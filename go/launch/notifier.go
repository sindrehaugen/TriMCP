package launch

import (
	"log/slog"
	"os"
)

// UserNotifier shows plain-language, native UI errors (Part 1 contract). No stack traces in dialogs.
type UserNotifier interface {
	// Error shows a blocking error dialog (or best-effort stderr in headless environments).
	Error(title, message string)
}

// LogNotifier logs only (CI / headless fallback).
type LogNotifier struct {
	Log *slog.Logger
}

func (l LogNotifier) Error(title, message string) {
	if l.Log != nil {
		l.Log.Error("user notification", "title", title, "message", message)
		return
	}
	_, _ = os.Stderr.WriteString(title + ": " + message + "\n")
}
