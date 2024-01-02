import gradio as gr
import re
import json
from modules import chat, shared, ui_chat
from modules.text_generation import generate_reply_HF, generate_reply_custom
import time
from collections import defaultdict

params = {
    "activate": True,
    "kernel": "python3",
    "jupyterlab": "localhost:8888",
    "jupyterlab_token": "secret",
}


outputs = defaultdict(dict)
waiting_for_computation = False
waiting_for_cell = 0
jupyter_cells = 1
input_evaluation = False


# counter added to all jupyter cells to map them later correctly to the outputs
def count_replacements(match):
    global jupyter_cells, outputs, waiting_for_cell, waiting_for_computation
    content = match[1]
    jupyter_cells += 1
    waiting_for_cell = jupyter_cells
    waiting_for_computation = True
    outputs[jupyter_cells]["input"] = match[0] 
    return f'<pre class="code" id="jupyter_cell_{jupyter_cells}" style="padding: 16px" data-executable="true" data-language="python">{content}</pre>'

# render the code cell in the frontend correctly for user inputs
def chat_input_modifier(text, visible_text, state):
    global waiting_for_computation, jupyter_cells, input_evaluation
    if not params['activate']:
        return text, visible_text
    vis_tex = visible_text
    visible_text = re.sub(r"```python\n(.*?)\n```", repl=count_replacements, string=visible_text, flags=re.S)
    if vis_tex != visible_text:
        # check if the user inputed a code cell
        input_evaluation = True
    return text, visible_text

# remove all the <pre class="code"> </pre> from the input
# otherwise the model is confused
def history_modifier(history):
    if len(history["internal"]) > 0:
        for i in range(0, len(history["internal"])):
            # find and replace all <pre>
            history["internal"][i][1] = re.sub(r"<pre class=\"code\" id=\"jupyter_cell_\d+?\" .*? data-executable=\"true\" data-language=\".*?\">(.*?)</pre>", r"```python\n\1\n```", string=history["internal"][i][1], flags=re.S)
    print(history)
    return history

# reset all values
def data_reset():
    global waiting_for_computation, waiting_for_cell, jupyter_cells, outputs
    waiting_for_computation = False
    waiting_for_cell = 0
    jupyter_cells = 1
    outputs = defaultdict(dict)

# react to frontend changes and keep state ~synced
def finished_exectution(jupyter_output):
    global waiting_for_computation, waiting_for_cell, jupyter_cells, outputs
    jupyter_output1 = str(jupyter_output)
    response_json = json.loads(jupyter_output1)
    if "reset" in response_json and response_json["reset"]: 
        # reset the dict if needed
        outputs = defaultdict(dict)
    id = int(response_json["textgen_id"])
    outputs[id]["output"] = response_json["output"]
    if waiting_for_cell == id:
        waiting_for_computation = False
    # print("json", outputs)

# insert the output into the context
def custom_generate_reply(question, original_question, seed, state, stopping_strings, is_chat):
    global update_history, waiting_for_computation, input_evaluation
    # print(question, original_question, seed, state, stopping_strings, is_chat)
    if shared.model.__class__.__name__ in ['LlamaCppModel', 'RWKVModel', 'ExllamaModel', 'Exllamav2Model',
                                           'CtransformersModel']:
        generate_func = generate_reply_custom
    else:
        generate_func = generate_reply_HF

    if not params['activate']:
        for reply in generate_func(question, original_question, seed, state, stopping_strings, is_chat=is_chat):
            yield reply
        return
    
    if input_evaluation:
        # if user put code into the promt evaluate it before generating an output
        # currently only works for 1 cell per user message
        input_evaluation = False
        while waiting_for_computation:
            # wait for the computation to end
            time.sleep(0.2)
        computation_result = outputs[list(outputs)[-1]]["output"]
        output_text = ""
        # for the output concat all parts that are text
        for output in outputs[list(outputs)[-1]]["output"]:
            if output["type"] == "text":
                output_text += output["data"]
        question = question.replace(outputs[list(outputs)[-1]]["input"], outputs[list(outputs)[-1]]["input"] + "\nResult:\n" + output_text)
    code_pattern = re.compile(r"```python\n(.*?)\n```", re.DOTALL)
    skip_return = False
    # maybe handle internal and visible state differently instead of changing the history afterwards
    previous_generation_internal = ""
    previous_generation_view = ""
    # loop if model needs multiple code blocks for one answer
    while True:
        for reply in generate_func(question, original_question, seed, state, stopping_strings, is_chat=is_chat):
            if code_pattern.search(reply) and params['activate']:
                # found code block
                previous_generation_internal += reply
                reply = re.sub(r"```python\n(.*?)\n```", repl=count_replacements, string=reply, flags=re.S)
                previous_generation_view += reply
                skip_return = True
                print("found code block", reply)
                yield previous_generation_view
                break
            # stream tokens
            yield previous_generation_view + reply
        if not skip_return:
            return
        else:
            # wait for cell to finish computation
            start_waiting = time.time()
            timeout = False
            # sometimes the ui does not update correctly, sending it multiple times fixes it.
            time.sleep(0.5)
            yield previous_generation_view
            time.sleep(0.5)
            yield previous_generation_view
            while waiting_for_computation:
                if time.time() - start_waiting > 30.0:
                    # timeout did not answer after 30 seconds
                    waiting_for_computation = False
                    timeout = True
                    print("timeout waiting for result")
                time.sleep(0.2)
            output_text = ""
            if timeout == False:
                # for the output concat all parts that are text
                for output in outputs[waiting_for_cell]["output"]:
                    if output["type"] == "text":
                        output_text += output["data"]
                    if output["type"] == "error":
                        print("an error occured", output["error_type"], output["data"])
                        output_text += output["error_type"] + "\n" + json.dumps(output["data"])
            else:
                output_text = "timeout waiting for computation"
            previous_generation_internal += "\nResult: " + output_text
            previous_generation_view += "\nResult: " + output_text
            question += previous_generation_internal
            # print(question)
            original_question = question
            skip_return = False
    return

# add global js script
def generate_js(file_name):
    js = f"""
    (() => {{
        let globalsScript = document.createElement("script");
        globalsScript.src = "file/extensions/{file_name}";
        document.head.appendChild(globalsScript);
    }})();
    """
    return js

# add css styles for thebe
def generate_css(file_name):
    css = f"""
    (() => {{
        let globalstyle = document.createElement("link");
        globalstyle.rel = "stylesheet";
        globalstyle.href = "file/extensions/{file_name}";
        document.head.appendChild(globalstyle);
    }})();
    """
    return css

# insert thebe header config
def generate_thebe_header():
    header_creator = """
    (() => {{
        let globalScript = document.createElement("script");
        globalScript.type = "text/x-thebe-config";
        globalScript.src = "";
        globalScript.innerHTML = "{'requestKernel': true, 'mountActivateWidget': true, 'mountStatusWidget': true, 'useJupyterLite': false, 'useBinder': false, 'kernelOptions': {  'name': 'python3'}, 'serverSettings': {  'baseUrl': 'http://localhost:8890',  'token': 'abc',  'wsUrl': 'ws://localhost:8890'}}";
        document.head.appendChild(globalScript);
    }})();
    """
    return header_creator


def ui():
    # generate the ui
    with gr.Blocks(analytics_enabled=False) as interface:
        # insert header
        # Load CSS and DOM element to be used as proxy between Gradio and the injected JS modules
        gr.HTML(value="<img src onerror='" + generate_css("CodeRunner/assets/thebe/main.css") + "'>")
        gr.HTML(value="<img src onerror='" + generate_css("CodeRunner/assets/thebe/thebe.css") + "'>")
        # https://github.com/oobabooga/text-generation-webui/discussions/941
        gr.HTML(value="<img src onerror='" + generate_js("CodeRunner/assets/require/require.js") + "'>")
        gr.HTML(value="<img src onerror='" + generate_js("CodeRunner/assets/thebe/index.js") + "'>")
        # script to handle Code Cells in UI
        gr.HTML(value="<img src onerror='" + generate_js("CodeRunner/assets/script.js") + "'>")

        # add hidden button for data return
        json_text = gr.Textbox(visible=False, elem_id="jupyter_data")
        datareturn = gr.Button(visible=False, value="jupyter_button_hidden", elem_id="jupyter_data_submit")
        datareturn.click(finished_exectution, inputs=json_text)
    # Gradio elements
    with gr.Accordion("CodeRunner"):
        with gr.Row():
            activate = gr.Checkbox(value=params['activate'], label='Activate CodeRunner')
            gr.HTML('<button class="lg secondary thebe-button" style="" onclick="jupyterConnect();" id="component-429">Connect</button>')
            textgen_reset = gr.Button("Reset")
            textgen_reset.click(data_reset)
        with gr.Row():
            jupyter_server_addr = gr.Textbox(show_label=False, value="localhost:8888", placeholder="localhost:8888", elem_id="jupyter_server")
            jupyter_server_token = gr.Textbox(show_label=False, value="secret", placeholder="secret-token", elem_id="jupyter_token")
            jupyter_server_kernel = gr.Textbox(show_label=False, value="python3", placeholder="kernel", elem_id="jupyter_kernel")
        with gr.Accordion("Status"):
            gr.HTML('<div class="thebe-activate"></div><div class="thebe-status"></div>')
            gr.HTML('<div class="hidden"><pre class="code" id="jupyter_cell_0" style="padding: 16px" data-executable="true" data-language="python">print("hello")</pre></div>')
            

    # Event functions to update the parameters in the backend
    activate.change(lambda x: params.update({"activate": x}), activate, None)
    # language.change(lambda x: params.update({"language string": language_codes[x]}), language, None)
    jupyter_server_addr.change(lambda x: params.update({"jupyterlab": x}), jupyter_server_addr, None)
    jupyter_server_token.change(lambda x: params.update({"jupyterlab_token": x}), jupyter_server_token, None)
    jupyter_server_kernel.change(lambda x: params.update({"jupyterlab_kernel": x}), jupyter_server_kernel, None)