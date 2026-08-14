package repository

// Repository interface for data access
type Repository interface {
	FindAll() ([]interface{}, error)
	FindByID(id string) (interface{}, error)
	Create(entity interface{}) error
	Update(id string, entity interface{}) error
	Delete(id string) error
}

// UserRepository handles user data operations
type UserRepository struct {
	db Database
}

// NewUserRepository creates a new user repository
func NewUserRepository(db Database) *UserRepository {
	return &UserRepository{db: db}
}

// FindAll retrieves all users
func (r *UserRepository) FindAll() ([]interface{}, error) {
	query := "SELECT * FROM users"
	return r.db.Query(query)
}

// FindByID retrieves a user by ID
func (r *UserRepository) FindByID(id string) (interface{}, error) {
	query := "SELECT * FROM users WHERE id = $1"
	return r.db.QueryOne(query, id)
}

// Create creates a new user
func (r *UserRepository) Create(entity interface{}) error {
	query := "INSERT INTO users (email, first_name, last_name) VALUES ($1, $2, $3)"
	user := entity.(map[string]string)
	return r.db.Exec(query, user["email"], user["first_name"], user["last_name"])
}

// Update updates an existing user
func (r *UserRepository) Update(id string, entity interface{}) error {
	query := "UPDATE users SET email = $1, first_name = $2, last_name = $3 WHERE id = $4"
	user := entity.(map[string]string)
	return r.db.Exec(query, user["email"], user["first_name"], user["last_name"], id)
}

// Delete deletes a user
func (r *UserRepository) Delete(id string) error {
	query := "DELETE FROM users WHERE id = $1"
	return r.db.Exec(query, id)
}

// Database interface for database operations
type Database interface {
	Query(query string, args ...interface{}) ([]interface{}, error)
	QueryOne(query string, args ...interface{}) (interface{}, error)
	Exec(query string, args ...interface{}) error
}
