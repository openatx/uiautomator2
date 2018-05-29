package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/pkg/errors"
	goadb "github.com/yosemite-open/go-adb"
)

var adb *goadb.Adb

const stfBinariesDir = "vendor/stf-binaries-master/node_modules"

func init() {
	var err error
	adb, err = goadb.New()
	if err != nil {
		log.Fatal(err)
	}
	serverVersion, err := adb.ServerVersion()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("adb server version: %d\n", serverVersion)
}

func initUiAutomator2(device *goadb.Device, serverAddr string) error {
	props, err := device.Properties()
	if err != nil {
		return err
	}
	sdk := props["ro.build.version.sdk"]
	abi := props["ro.product.cpu.abi"]
	pre := props["ro.build.version.preview_sdk"]
	// arch := props["ro.arch"]
	log.Printf("product model: %s\n", props["ro.product.model"])

	if pre != "" && pre != "0" {
		sdk += pre
	}
	log.Println("Install minicap and minitouch")
	if err := initSTFMiniTools(device, abi, sdk); err != nil {
		return errors.Wrap(err, "mini(cap|touch)")
	}
	log.Println("Install app-uiautomator[-test].apk")
	if err := initUiAutomatorAPK(device); err != nil {
		return errors.Wrap(err, "app-uiautomator[-test].apk")
	}
	log.Println("Install atx-agent")
	atxAgentPath := "vendor/atx-agent"
	if err := writeFileToDevice(device, atxAgentPath, "/data/local/tmp/atx-agent", 0755); err != nil {
		return errors.Wrap(err, "atx-agent")
	}

	args := []string{"-d"}
	if serverAddr != "" {
		args = append(args, "-t", serverAddr)
	}
	output, err := device.RunCommand("/data/local/tmp/atx-agent", args...)
	output = strings.TrimSpace(output)
	if err != nil {
		return errors.Wrap(err, "start atx-agent")
	}
	serial, _ := device.Serial()
	fmt.Println(serial, output)
	return nil
}

func writeFileToDevice(device *goadb.Device, src, dst string, mode os.FileMode) error {
	f, err := os.Open(src)
	if err != nil {
		return err
	}
	defer f.Close()
	dstTemp := dst + ".tmp-magic1231x"
	_, err = device.WriteToFile(dstTemp, f, mode)
	if err != nil {
		device.RunCommand("rm", dstTemp)
		return err
	}
	// use mv to prevent "text busy" error
	_, err = device.RunCommand("mv", dstTemp, dst)
	return err
}

func initMiniTouch(device *goadb.Device, abi string) error {
	srcPath := fmt.Sprintf(stfBinariesDir+"/minitouch-prebuilt/prebuilt/%s/bin/minitouch", abi)
	return writeFileToDevice(device, srcPath, "/data/local/tmp/minitouch", 0755)
}

func initSTFMiniTools(device *goadb.Device, abi, sdk string) error {
	soSrcPath := fmt.Sprintf(stfBinariesDir+"/minicap-prebuilt/prebuilt/%s/lib/android-%s/minicap.so", abi, sdk)
	err := writeFileToDevice(device, soSrcPath, "/data/local/tmp/minicap.so", 0644)
	if err != nil {
		return err
	}
	binSrcPath := fmt.Sprintf(stfBinariesDir+"/minicap-prebuilt/prebuilt/%s/bin/minicap", abi)
	err = writeFileToDevice(device, binSrcPath, "/data/local/tmp/minicap", 0755)
	if err != nil {
		return err
	}
	touchSrcPath := fmt.Sprintf(stfBinariesDir+"/minitouch-prebuilt/prebuilt/%s/bin/minitouch", abi)
	return writeFileToDevice(device, touchSrcPath, "/data/local/tmp/minitouch", 0755)
}

func installAPK(device *goadb.Device, localPath string) error {
	dstPath := "/data/local/tmp/" + filepath.Base(localPath)
	if err := writeFileToDevice(device, localPath, dstPath, 0644); err != nil {
		return err
	}
	defer device.RunCommand("rm", dstPath)
	output, err := device.RunCommand("pm", "install", "-r", "-t", dstPath)
	if err != nil {
		return err
	}
	if !strings.Contains(output, "Success") {
		return errors.Wrap(errors.New(output), "apk-install")
	}
	return nil
}

func initUiAutomatorAPK(device *goadb.Device) (err error) {
	_, er1 := device.StatPackage("com.github.uiautomator")
	_, er2 := device.StatPackage("com.github.uiautomator.test")
	if er1 == nil && er2 == nil {
		log.Println("APK already installed, Skip. Uninstall apk manually if you want to reinstall apk")
		return
	}
	err = installAPK(device, "vendor/app-uiautomator.apk")
	if err != nil {
		return
	}
	return installAPK(device, "vendor/app-uiautomator-test.apk")
}

func startService(device *goadb.Device) (err error) {
	_, err = device.RunCommand("am", "startservice", "-n", "com.github.uiautomator/.Service")
	return err
}

func watchAndInit(serverAddr string) {
	watcher := adb.NewDeviceWatcher()
	for event := range watcher.C() {
		if event.CameOnline() {
			log.Printf("Device %s came online", event.Serial)
			device := adb.Device(goadb.DeviceWithSerial(event.Serial))
			log.Printf("Init device")
			if err := initUiAutomator2(device, serverAddr); err != nil {
				log.Printf("Init error: %v", err)
				continue
			} else {
				log.Printf("Init Success")
				startService(device)
			}
		}
		if event.WentOffline() {
			log.Printf("Device %s went offline", event.Serial)
		}
	}
	if watcher.Err() != nil {
		log.Fatal(watcher.Err())
	}
}

func main() {
	serverAddr := flag.String("server", "", "atx-server address(must be ip:port) eg: 10.0.0.1:7700")
	flag.Parse()

	fmt.Println("u2init version 20180330")
	wd, _ := os.Getwd()
	log.Println("Add adb.exe to PATH +=", filepath.Join(wd, "vendor"))
	newPath := fmt.Sprintf("%s%s%s", os.Getenv("PATH"), string(os.PathListSeparator), filepath.Join(wd, "vendor"))
	os.Setenv("PATH", newPath)

	watchAndInit(*serverAddr)
}
