package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type CacheManager struct {
	client *redis.Client
	ctx    context.Context
}

func NewCacheManager(addr string) *CacheManager {
	client := redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: "",
		DB:       0,
	})

	return &CacheManager{
		client: client,
		ctx:    context.Background(),
	}
}

func (cm *CacheManager) Close() error {
	return cm.client.Close()
}

func (cm *CacheManager) Get(key string, dest interface{}) error {
	val, err := cm.client.Get(cm.ctx, key).Result()
	if err != nil {
		if err == redis.Nil {
			return nil
		}
		return fmt.Errorf("failed to get from cache: %w", err)
	}

	return json.Unmarshal([]byte(val), dest)
}

func (cm *CacheManager) Set(key string, value interface{}, ttl time.Duration) error {
	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("failed to marshal value: %w", err)
	}

	return cm.client.Set(cm.ctx, key, data, ttl).Err()
}

func (cm *CacheManager) Delete(key string) error {
	return cm.client.Del(cm.ctx, key).Err()
}

func (cm *CacheManager) Exists(key string) (bool, error) {
	count, err := cm.client.Exists(cm.ctx, key).Result()
	return count > 0, err
}

func (cm *CacheManager) GetOrSet(key string, dest interface{}, factory func() (interface{}, error), ttl time.Duration) error {
	err := cm.Get(key, dest)
	if err == nil {
		return nil
	}

	value, err := factory()
	if err != nil {
		return fmt.Errorf("factory failed: %w", err)
	}

	if err := cm.Set(key, value, ttl); err != nil {
		return fmt.Errorf("failed to set cache: %w", err)
	}

	// Unmarshal the newly set value
	return cm.Get(key, dest)
}

func main() {
	cm := NewCacheManager("localhost:6379")
	defer cm.Close()

	type User struct {
		ID   int    `json:"id"`
		Name string `json:"name"`
	}

	user := User{ID: 1, Name: "John"}
	err := cm.Set("user:1", user, time.Hour)
	if err != nil {
		panic(err)
	}

	var cachedUser User
	err = cm.Get("user:1", &cachedUser)
	if err != nil {
		panic(err)
	}

	fmt.Printf("Cached user: %+v\n", cachedUser)
}
