package main

import (
	"fmt"
	"strings"
	"unicode"
)

type StringUtils struct{}

func NewStringUtils() *StringUtils {
	return &StringUtils{}
}

func (s *StringUtils) CamelToSnake(name string) string {
	var result []rune
	for i, r := range name {
		if unicode.IsUpper(r) && i > 0 {
			result = append(result, '_')
		}
		result = append(result, unicode.ToLower(r))
	}
	return string(result)
}

func (s *StringUtils) SnakeToCamel(name string) string {
	parts := strings.Split(name, "_")
	for i, part := range parts {
		if len(part) > 0 {
			parts[i] = strings.Title(part)
		}
	}
	return strings.Join(parts, "")
}

func (s *StringUtils) Truncate(text string, maxLen int, suffix string) string {
	if len(text) <= maxLen {
		return text
	}
	return text[:maxLen-len(suffix)] + suffix
}

func (s *StringUtils) SplitIntoChunks(text string, chunkSize int) []string {
	var chunks []string
	for i := 0; i < len(text); i += chunkSize {
		end := i + chunkSize
		if end > len(text) {
			end = len(text)
		}
		chunks = append(chunks, text[i:end])
	}
	return chunks
}

func main() {
	utils := NewStringUtils()
	fmt.Println(utils.CamelToSnake("CamelCase"))
	fmt.Println(utils.SnakeToCamel("snake_case"))
	fmt.Println(utils.Truncate("Hello World", 5, "..."))
}
