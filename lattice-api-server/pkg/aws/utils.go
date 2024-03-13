package aws

import (
	"fmt"
	"lattice-api-server/pkg/types"
	"os"
	"strconv"
)

const (
	awsRegion              = "AWS_REGION"
	awsS3Bucket            = "AWS_S3_BUCKET"
	awsEKSClusterName      = "AWS_EKS_CLUSTER_NAME"
	awsEKSWorkerNodeGroup  = "AWS_EKS_WORKER_NODEGROUP"
	maxCluserSizeEnv       = "MAX_CLUSTER_SIZE"
	DefaultBucketName      = "lattice-storage"
	DefaultRegion          = "ap-southeast-1"
	DefaultClusterName     = "dev-cluster"
	DefaultWorkerNodeGroup = "worker-nodegroup"
	DefaultMaxClusterSize  = 12
)

// generate the AWS S3 bucket endpoint
func GenerateS3Endpoint(job *types.TrainingJob, bucketName string) string {
	return fmt.Sprintf("s3://%s/%s.zip", bucketName, job.Name)
}

// get the AWS S3 bucket name from the environment variables
// by default "lattice-checkpoint-storage"
func GetAWSS3Bucket() string {
	if envValue, ok := os.LookupEnv(awsS3Bucket); ok {
		return envValue
	} else {
		return DefaultBucketName
	}
}

// get the AWS region from the environment variables
// by default "ap-southeast-1"
func GetAWSRegion() string {
	if envValue, ok := os.LookupEnv(awsRegion); ok {
		return envValue
	} else {
		return DefaultRegion
	}
}

// get the AWS EKS cluster name from the environment variables
// by default "dev-cluster"
func GetAWSEKSClusterName() string {
	if envValue, ok := os.LookupEnv(awsEKSClusterName); ok {
		return envValue
	} else {
		return DefaultClusterName
	}
}

// get the AWS EKS worker nodegroup from the environment variables
// by default "worker-nodegroup"
func GetAWSEKSWorkerNodegroup() string {
	if envValue, ok := os.LookupEnv(awsEKSWorkerNodeGroup); ok {
		return envValue
	} else {
		return DefaultWorkerNodeGroup
	}
}

// get the max cluster size from the environment variables
// by default 12
func GetMaxClusterSize() int64 {
	if envValue, ok := os.LookupEnv(maxCluserSizeEnv); ok {
		// convert the string envValue to int
		value, err := strconv.Atoi(envValue)
		if err != nil {
			return DefaultMaxClusterSize
		} else {
			return int64(value)
		}
	} else {
		return DefaultMaxClusterSize
	}
}
