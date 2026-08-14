package model

import "time"

// Document represents a searchable document
type Document struct {
	ID          string    `json:"id"`
	Title       string    `json:"title"`
	Body        string    `json:"body"`
	Author      string    `json:"author"`
	Tags        []string  `json:"tags"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
	Visibility  string    `json:"visibility"`
	ACLTerms    []string  `json:"acl_terms"`
}

// User represents a user in the system
type User struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	FirstName string    `json:"first_name"`
	LastName  string    `json:"last_name"`
	Role      string    `json:"role"`
	CreatedAt time.Time `json:"created_at"`
}

// SearchQuery represents a search request
type SearchQuery struct {
	Query    string            `json:"query"`
	Page     int               `json:"page"`
	PageSize int               `json:"page_size"`
	Sort     string            `json:"sort"`
	Filters  map[string]string `json:"filters"`
}

// SearchResult represents search results
type SearchResult struct {
	Documents []Document `json:"documents"`
	Total     int        `json:"total"`
	Page      int        `json:"page"`
	PageSize  int        `json:"page_size"`
}
