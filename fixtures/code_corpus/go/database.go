package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"time"

	_ "github.com/lib/pq"
)

type DatabaseManager struct {
	db *sql.DB
}

func NewDatabaseManager(dsn string) (*DatabaseManager, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	if err = db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	return &DatabaseManager{db: db}, nil
}

func (dm *DatabaseManager) Close() error {
	return dm.db.Close()
}

func (dm *DatabaseManager) Query(ctx context.Context, query string, args ...interface{}) (*sql.Rows, error) {
	return dm.db.QueryContext(ctx, query, args...)
}

func (dm *DatabaseManager) QueryRow(ctx context.Context, query string, args ...interface{}) *sql.Row {
	return dm.db.QueryRowContext(ctx, query, args...)
}

func (dm *DatabaseManager) Exec(ctx context.Context, query string, args ...interface{}) (sql.Result, error) {
	return dm.db.ExecContext(ctx, query, args...)
}

func (dm *DatabaseManager) BeginTx(ctx context.Context) (*sql.Tx, error) {
	return dm.db.BeginTx(ctx, nil)
}

type User struct {
	ID        int       `json:"id"`
	Email     string    `json:"email"`
	Username  string    `json:"username"`
	CreatedAt time.Time `json:"created_at"`
}

func (dm *DatabaseManager) GetUser(ctx context.Context, id int) (*User, error) {
	query := `SELECT id, email, username, created_at FROM users WHERE id = $1`
	row := dm.QueryRow(ctx, query, id)

	var user User
	err := row.Scan(&user.ID, &user.Email, &user.Username, &user.CreatedAt)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to scan user: %w", err)
	}

	return &user, nil
}

func (dm *DatabaseManager) CreateUser(ctx context.Context, email, username string) (int, error) {
	query := `INSERT INTO users (email, username) VALUES ($1, $2) RETURNING id`
	var id int
	err := dm.QueryRow(ctx, query, email, username).Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("failed to create user: %w", err)
	}
	return id, nil
}

func main() {
	dsn := "postgres://user:password@localhost:5432/mydb"
	dm, err := NewDatabaseManager(dsn)
	if err != nil {
		log.Fatal(err)
	}
	defer dm.Close()

	ctx := context.Background()
	user, err := dm.GetUser(ctx, 1)
	if err != nil {
		log.Fatal(err)
	}

	if user != nil {
		fmt.Printf("User: %+v\n", user)
	}
}
