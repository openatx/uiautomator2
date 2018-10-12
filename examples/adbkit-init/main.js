'use strict'

var Promise = require('bluebird')
var adb = require('adbkit')
var client = adb.createClient()
var util = require('util')
const { spawn } = require("child_process")
var argv = require('minimist')(process.argv.slice(2))

const serverAddr = argv.server; // Usage: node main.js --server $SERVER_ADDR

function initDevice(device) {
  if (device.type != 'device') {
    return
  }
  client.shell(device.id, 'am start -a android.intent.action.VIEW -d http://www.stackoverflow.com')
    .then(adb.util.readAll)
    .then(function(output) {
      var args = ["-m", "uiautomator2", "init", "--serial", device.id]
      if (serverAddr) {
        args.push("--server", serverAddr);
      }
      const child = spawn("python", args);
      child.stdout.on("data", data => {
        process.stdout.write(data)
      })
      child.stderr.on("data", data => {
        process.stderr.write(data)
      })
      child.on('close', code => {
        util.log(`child process exited with code ${code}`);
      });
    })
}

util.log("tracking device")
if (serverAddr) {
  util.log("server %s", serverAddr)
}

client.trackDevices()
  .then(function(tracker) {
    tracker.on('add', function(device) {
      util.log("Device %s(%s) was plugged in", device.id, device.type)
      initDevice(device)
    })
    tracker.on('remove', function(device) {
      util.log('Device %s was unplugged', device.id)
    })
    tracker.on("change", function(device) {
      util.log('Device %s was changed to %s', device.id, device.type)
      initDevice(device)
    })
    tracker.on('end', function() {
      util.log('Tracking stopped')
    })
  })