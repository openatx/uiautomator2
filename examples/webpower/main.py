# coding: utf-8
#

import flask
import requests


app = flask.Flask(__name__)


@app.route('/')
def index():
    return flask.render_template('index.html')


@app.route('/battery_level/<ip>')
def battery_level(ip):
    r = requests.get('http://'+ip+':7912/info').json()
    return str(r.get('battery').get('level'))