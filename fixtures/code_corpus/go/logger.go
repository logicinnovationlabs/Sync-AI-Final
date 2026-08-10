package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"
)

type LogLevel int

const (
	DEBUG LogLevel = iota
	INFO
	WARN
	ERROR
)

type Logger struct {
	name  string
	level LogLevel
}

type LogEntry struct {
	Timestamp time.Time              `json:"timestamp"`
	Level     string                 `json:"level"`
	Logger    string                 `json:"logger"`
	Message   string                 `json:"message"`
	Context   map[string]interface{} `json:"context,omitempty"`
}

func NewLogger(name string, level LogLevel) *Logger {
	return &Logger{
		name:  name,
		level: level,
	}
}

func (l *Logger) log(level LogLevel, message string, context map[string]interface{}) {
	if level < l.level {
		return
	}

	entry := LogEntry{
		Timestamp: time.Now(),
		Level:     l.levelToString(level),
		Logger:    l.name,
		Message:   message,
		Context:   context,
	}

	data, err := json.Marshal(entry)
	if err != nil {
		log.Printf("Failed to marshal log entry: %v", err)
		return
	}

	fmt.Println(string(data))
}

func (l *Logger) levelToString(level LogLevel) string {
	switch level {
	case DEBUG:
		return "DEBUG"
	case INFO:
		return "INFO"
	case WARN:
		return "WARN"
	case ERROR:
		return "ERROR"
	default:
		return "UNKNOWN"
	}
}

func (l *Logger) Debug(message string, context map[string]interface{}) {
	l.log(DEBUG, message, context)
}

func (l *Logger) Info(message string, context map[string]interface{}) {
	l.log(INFO, message, context)
}

func (l *Logger) Warn(message string, context map[string]interface{}) {
	l.log(WARN, message, context)
}

func (l *Logger) Error(message string, context map[string]interface{}) {
	l.log(ERROR, message, context)
}

func main() {
	logger := NewLogger("app", INFO)
	logger.Info("Application started", map[string]interface{}{"version": "1.0.0"})
	logger.Error("Something went wrong", map[string]interface{}{"error": "test error"})
}
