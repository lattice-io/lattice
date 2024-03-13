package test

import (
	"fmt"
	"testing"
)

func sayHello(name string) string {
	return fmt.Sprintf("Hello %s", name)
}

// Example unit test of golang.
func Test_helloWorld(t *testing.T) {
	name := "Bob"
	want := "Hello Bob"

	if got := sayHello(name); got != want {
		t.Errorf("hello() = %q, want %q", got, want)
	}
}
