# Code Runner

- allows you to run code in the chat interface
- needs a jupyter server to connect to
- runs the code in a jupyter kernel
- allows the use of ipywidgets

# Setup
To install it in text-generation-webui, go to the extensions folder and clone this repo.
All requirements should already be installed.
Afterwards install a jupyterlab server. I recommend docker because it does not screw with your personal files.

```bash
# install extension
$ cd extensions/
$ git clone ...
# setup jupyter server
$ cd CodeRunner
$ docker compose up
```

! Currently a version of text-generation-webui is needed that does not change replies with code cells in them.

# Usage
Enable the extension in the `Session tab`.
In the `Chat tab` scroll to the bottom and type in the jupyter `server address` and the `token`.
Click on `Connect` above.
Afterwards you can test if it works in the Status section below by clicking on `run`.
If it works you can ask the model to generate code and the code should be evaluated inline with the response.

To get better results use a Character that has some examples how to use code cells:
~~~
The AI always create a python program that computes the output instead of answering it directly.

Question:
What is 10 + 5?
Answer:
```python
print(10 + 5)
```
Result: 15
If you add 10 and 5 the result is 15

Question:
What is 30*10?
Answer:
```python
print(30 * 10)
```
Result: 300
If you multiply 30 and 10 the result is 300
~~~

# How it works
It works by using thebe to interact with a jupyter server that executes the python code and sends back the result.
If the model generates a code block it is changed to a thebe code cell, this is detected by the browser that sends it to jupyter to execute. The response is displayed in the Browser and also send back to the model, this output is injected into the context and the model continues with the response.

# Limitations
- There is a 30 second timeout for exection of code cells, the cell might compute it result later, but the answer can not be injected later into the context.
- Each time the frontend changes everything is recomputed, because the output display is lost.

# Build
Currently thebe is already compiled in the assets if you want to build it yourself you can clone thebe from github.
I made some changes to thebe so you need this PR: https://github.com/executablebooks/thebe/pull/725
After it compiled you need to take the `index.js` file and if you dont want to load `require.js` from cloudflare eachtime you use it, you have to replace `https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.6/require.min.js` by `file/extensions/CodeRunner/assets/require/require.js`. Then copy `index.js` and `mathjax.js` into `assets/thebe/`.
