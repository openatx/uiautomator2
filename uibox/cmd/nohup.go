/*
Copyright © 2024 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"

	"github.com/spf13/cobra"
)

// nohupCmd represents the nohup command
var nohupCmd = &cobra.Command{
	Use: "nohup",

	Short: "invoke a utility immune to hangups",
	Long: `The nohup utility invokes utility with its arguments and at this time sets the signal SIGHUP to be ignored.
If the standard output is a terminal, the standard output is appended to the file nohup.out in the current directory.
If standard error is a terminal, it is directed to the same place as the standard output.`,
	DisableFlagParsing: true,
	Run:                nohupRun,
}

func init() {
	rootCmd.AddCommand(nohupCmd)

	nohupCmd.SetUsageTemplate(`Usage: nohup COMMAND [ARG]...`)
}

func nohupRun(_ *cobra.Command, args []string) {
	// Ignore SIGHUP signal
	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	// Start the command
	if err := cmd.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Error starting command: %v\n", err)
		os.Exit(1)
	}

	// Wait for the command to finish
	if err := cmd.Wait(); err != nil {
		fmt.Fprintf(os.Stderr, "Error waiting for command: %v\n", err)
		os.Exit(1)
	}
}
