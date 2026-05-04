package main

import (
	"os"

	"github.com/trimcp/tri-stack/trimcp-launch/internal/config"
	"github.com/trimcp/tri-stack/trimcp-launch/internal/logx"
	"github.com/trimcp/tri-stack/trimcp-launch/internal/notify"
	"github.com/trimcp/tri-stack/trimcp-launch/internal/paths"
)

// Phase 4 Part 1: validates mode.txt + .env merge, logging, and notifier wiring.
func main() {
	logger, logFile, err := logx.Setup(os.Stderr)
	if err != nil {
		notify.New().Error("TriMCP", "failed to open log file: "+err.Error())
		os.Exit(1)
	}
	defer logFile.Close()

	modePath, err := paths.ModeFilePath()
	if err != nil {
		logger.Error("mode path", "err", err)
		notify.New().Error("TriMCP", err.Error())
		os.Exit(1)
	}
	envPath, err := paths.EnvFilePath()
	if err != nil {
		logger.Error("env path", "err", err)
		notify.New().Error("TriMCP", err.Error())
		os.Exit(1)
	}

	mode, err := config.ReadMode(modePath)
	if err != nil {
		logger.Error("read mode", "path", modePath, "err", err)
		notify.New().Error("TriMCP — mode.txt", err.Error())
		os.Exit(1)
	}
	logger.Info("mode loaded", "mode", string(mode), "file", modePath)

	merged, err := config.MergeEnv(envPath)
	if err != nil {
		logger.Error("merge .env", "path", envPath, "err", err)
		notify.New().Error("TriMCP — .env", err.Error())
		os.Exit(1)
	}
	logger.Info(".env merged", "path", envPath, "env_count", len(merged))

	logger.Info("trimcp-launch Part 1 ready", "mode", string(mode))
}
