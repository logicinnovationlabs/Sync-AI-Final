package service

import "errors"

// Service handles business logic
type Service struct {
	repo Repository
}

// Repository interface
type Repository interface {
	FindAll() ([]interface{}, error)
	FindByID(id string) (interface{}, error)
	Create(entity interface{}) error
}

// NewService creates a new service
func NewService(repo Repository) *Service {
	return &Service{repo: repo}
}

// GetAll retrieves all entities
func (s *Service) GetAll() ([]interface{}, error) {
	return s.repo.FindAll()
}

// GetByID retrieves an entity by ID
func (s *Service) GetByID(id string) (interface{}, error) {
	if id == "" {
		return nil, errors.New("id cannot be empty")
	}
	return s.repo.FindByID(id)
}

// Create creates a new entity
func (s *Service) Create(entity interface{}) error {
	if entity == nil {
		return errors.New("entity cannot be nil")
	}
	return s.repo.Create(entity)
}

// Process performs business logic
func (s *Service) Process() error {
	// Business logic here
	return nil
}
