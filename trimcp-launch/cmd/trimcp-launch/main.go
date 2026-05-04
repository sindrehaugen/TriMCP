// trimcp-launch is the mode-aware MCP stdio shim (TriMCP Enterprise Deployment Plan §6.4).
package main

import (
	"context"
	"errors"
	"log/slog"
	"os"

	"github.com/trimcp/tri-stack/launch"
)

func main() {
	log, f, err := launch.SetupLogger(os.Stderr)
	if err != nil {
		_, _ = os.Stderr.WriteString("trimcp-launch: logger: " + err.Error() + "\n")
		os.Exit(1)
	}
	if f != nil {
		defer func() { _ = f.Close() }()
	}

	ctx, stop := notifyRootContext()
	defer stop()

	n := launch.NewPlatformNotifier(log)
	if err := launch.Run(ctx, n, log); err != nil {
		if errors.Is(err, context.Canceled) {
			os.Exit(0)
		}
		log.Error("launch_failed", slog.String("err", err.Error()))
		os.Exit(1)
	}
}
