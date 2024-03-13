package util

import "os"

// GetEnv get the system environment variable.
func GetEnv(key string) string {
	value := os.Getenv(key)
	if len(value) != 0 {
		return value
	}
	return ""
}

// Get the system environment variable with a default value
func GetEnvWithDefault(key string, deft string) string {
	if envValue, ok := os.LookupEnv(key); ok {
		return envValue
	} else {
		return deft
	}
}
