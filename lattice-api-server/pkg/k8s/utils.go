package k8s

import "os"

const (
	s3ServiceAccount        = "AWS_S3_SERVICE_ACCOUNT"
	defaultS3ServiceAccount = "s3"
)

// get the name of S3 irsa service account in the cluster
// by default "s3"
func GetS3ServiceAccount() string {
	if envValue, ok := os.LookupEnv(s3ServiceAccount); ok {
		return envValue
	} else {
		return defaultS3ServiceAccount
	}
}
