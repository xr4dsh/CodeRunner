const delay = ms => new Promise(res => setTimeout(res, ms));
let jupyter_timeout_id = 0;

/*
* Connect to the jupyter server
* to use binder or jupyter lite change the config below
*/
async function jupyterConnect(){
  let secure = ""; // set to "s" if secure else set "" 
  let server = document.getElementById("jupyter_server").querySelectorAll("textarea")[0].value;
  let server_token = document.getElementById("jupyter_token").querySelectorAll("textarea")[0].value;
  let jupyter_kernel = document.getElementById("jupyter_kernel").querySelectorAll("textarea")[0].value;

  let config = {
    bootstrap: false,
    preRenderHook: false,
    predefinedOutput: false,
    outputSelector: '[data-output]',
    requestKernel: true,
    mountActivateWidget: true,
    mountStatusWidget: true,
    useJupyterLite: false,
    useBinder: false,
    kernelOptions: {
      name: jupyter_kernel,
      kernelName: jupyter_kernel,
    },
    serverSettings: {
      baseUrl: "http://"+server,
      wsUrl: "ws://"+server,
      token: server_token,
    },
    selector: "[data-executable]",
    stripPrompts: false,
    mathjaxUrl: "file/extensions/CodeRunner/assets/thebe/mathjax.js",
    requirejsUrl: "file/extensions/CodeRunner/assets/require/require.js",
    mathjaxConfig: "TeX-AMS_CHTML-full,Safe",
    codeMirrorConfig: {},
  };
  window.thebe.configuration = config;

  // start setup
  window.thebe.mountStatusWidget();
  window.thebe.bootstrap(config);
  
  // add callback for finished cells
  window.thebe.on("status", async function (evt, data) {
    if(data.status == "idle" && data.message == "Completed"){
      // Send outputs back to gradio backend via button click event
      for (let i = 0; i < window.thebe.notebook.cells.length; i++) {
        console.log("sending value for cell", i);
        const cell = window.thebe.notebook.cells[i];
        await jupyterSendDataBack(JSON.stringify(jupyterExtractOutputData(cell.id)));
      };
    }
  });

  // add callback for onchange of the chat
  let jupyter_mutObs = new MutationObserver(async function() {
    // only execute cells if nothing was executed for some time
    clearTimeout(jupyter_timeout_id);
    jupyter_timeout_id = setTimeout(async()=>{await jupyterNewCode();}, 500);
  });
  jupyter_mutObs.observe(document.getElementById("chat-tab"), {childList:true, subtree: true});
  
  // execute all cells on start up to fill in the session and connection parameters
  delay(500);
  await window.thebe.notebook.executeAll();
}

// detect new code
async function jupyterNewCode(){
  // are there new cells?
  if (window.thebe.findCells(window.thebe.configuration.selector, window.thebe.configuration.outputSelector).length > 0) {
    window.thebe.replaceCells(window.thebe.configuration);
    delay(250);
    await window.thebe.notebook.executeAll();
  }
}

// sent a value back to the python backend
async function jupyterSendDataBack(data){
  document.getElementById("jupyter_data").querySelector("textarea").value = data;
  document.getElementById("jupyter_data").querySelector("textarea").dispatchEvent(new Event("input"));
  await delay(200);
  document.getElementById("jupyter_data_submit").click();
  await delay(200);
}

// get the cell output
function jupyterExtractOutputData(cell_id){
  let cell = window.thebe.notebook.getCellById(cell_id);
  let outputs = cell.outputs;
  computation_result = []
  outputs.forEach(output => {
    if (output.output_type == "display_data") {
      // if an image was created and should be send back 
      // has to be copied from the dom, can change with interactive application
      console.info("retrieve image not implemented");
      computation_result.push({"type": "image", "data": "image handling is not implemented yet"});
    } else {
      // get text outputs
      if (output.output_type == "execution_result"){
        computation_result.push({"type": "text", "data": output.data["text/plain"]});
      }else if (output.output_type == "stream") {
        computation_result.push({"type": "text", "data": output.text});
      }else if (output.output_type == "error") {
        computation_result.push({"type": "error", "data": output.traceback, "error_type": output.ename, "error_value": output.evalue});
      } else {
        console.error("not implemented");
      }
    }
  });
  // get the id to match the output to the input
  cell_index = window.thebe.notebook.cells.indexOf(window.thebe.notebook.getCellById(cell_id));
  textgen_index = cell.area.node.parentElement.parentElement.parentElement.id.split("_").at(-1);
  return {id: cell_index, textgen_id: textgen_index, output: computation_result};
}