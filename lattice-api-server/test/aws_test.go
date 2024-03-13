package test

import (
	"lattice-api-server/pkg/aws"
	"net/http"
	"os"
	"testing"
)

// only for testing purpose.
const (
	regionSG   = "us-east-1"
	bucketName = "breezeml-testing"
	objectKey  = "test.zip"
)

// Remember to set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for this test.
func TestGeneratePresignedURL(t *testing.T) {
	url, err := aws.GeneratePresignedURL(bucketName, objectKey, regionSG, aws.HOUR)
	if err != nil {
		t.Errorf("Error generating presigned URL: %v", err)
	}

	r, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		t.Fatal(err)
	}

	resp, err := http.DefaultClient.Do(r)
	if err != nil {
		t.Fatal(err)
	}

	if resp.StatusCode != http.StatusOK {
		_ = resp.Write(os.Stdout)
		t.Fatal(resp.Status)
	}
}
