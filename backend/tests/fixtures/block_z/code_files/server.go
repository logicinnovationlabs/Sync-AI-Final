package main

import (
	"fmt"
	"log"
	"net/http"
	"encoding/json"
	"time"
)

// Server represents the HTTP server
type Server struct {
	router *http.ServeMux
	port   int
}

// NewServer creates a new HTTP server
func NewServer(port int) *Server {
	return &Server{
		router: http.NewServeMux(),
		port:   port,
	}
}

// RegisterRoutes registers all HTTP routes
func (s *Server) RegisterRoutes() {
	s.router.HandleFunc("/health", s.handleHealth)
	s.router.HandleFunc("/api/users", s.handleUsers)
	s.router.HandleFunc("/api/search", s.handleSearch)
}

// handleHealth handles health check requests
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	response := map[string]interface{}{
		"status": "ok",
		"time":   time.Now().Unix(),
	}
	
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// handleUsers handles user-related requests
func (s *Server) handleUsers(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		s.getUsers(w, r)
	case http.MethodPost:
		s.createUser(w, r)
	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

// getUsers retrieves all users
func (s *Server) getUsers(w http.ResponseWriter, r *http.Request) {
	users := []map[string]string{
		{"id": "1", "name": "Alice"},
		{"id": "2", "name": "Bob"},
	}
	
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(users)
}

// createUser creates a new user
func (s *Server) createUser(w http.ResponseWriter, r *http.Request) {
	var user map[string]string
	if err := json.NewDecoder(r.Body).Decode(&user); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	
	user["id"] = fmt.Sprintf("%d", time.Now().Unix())
	
	w.Header().Set("Content-Type", "application/json")
	w.WriteStatus(http.StatusCreated)
	json.NewEncoder(w).Encode(user)
}

// handleSearch handles search requests
func (s *Server) handleSearch(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("q")
	
	results := map[string]interface{}{
		"query":   query,
		"results": []string{"result1", "result2", "result3"},
		"count":   3,
	}
	
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(results)
}

// Start starts the HTTP server
func (s *Server) Start() error {
	addr := fmt.Sprintf(":%d", s.port)
	log.Printf("Starting server on %s", addr)
	return http.ListenAndServe(addr, s.router)
}

func main() {
	server := NewServer(8080)
	server.RegisterRoutes()
	
	if err := server.Start(); err != nil {
		log.Fatal(err)
	}
}
