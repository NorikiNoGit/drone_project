from flask import Flask, jsonify
import logging

class DataHolder:
    def __init__(self):
        self.data = {}

    def update_data(self, new_data):
        self.data = new_data

    def get_data(self):
        return self.data

app = Flask(__name__)

data_holder = DataHolder()

# logをerror以下を表示しないようにする。
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/', methods=['GET'])
def home():
    data = data_holder.get_data()
    return jsonify(data), 200

def api_server_run():
    app.run(debug=False, port=50111, threaded=True)
