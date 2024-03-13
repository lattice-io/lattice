package aws

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"io"
	"path/filepath"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/eks"
	"github.com/aws/aws-sdk-go/service/s3"
)

const (
	HOUR = time.Hour
	DAY  = time.Hour * 24
)

// GeneratePresignedURL generates a presigned URL for an S3 object with the given bucket name, object key,
// and expiration time (in seconds).
func GeneratePresignedURL(bucketName, objectKey, region string, expiration time.Duration) (string, error) {
	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(region),
		// Put the credentials here.
		//Credentials: credentials.NewStaticCredentials("ID", "Key", ""),
		LogLevel: aws.LogLevel(aws.LogDebugWithHTTPBody),
	})
	if err != nil {
		return "", err
	}

	svc := s3.New(sess)
	req, _ := svc.GetObjectRequest(&s3.GetObjectInput{
		Bucket: aws.String(bucketName),
		Key:    aws.String(objectKey),
	})

	urlStr, err := req.Presign(expiration)

	if err != nil {
		return "", err
	}

	return urlStr, nil
}

// UploadZipManager uploads a extracted zip file to S3 bucket with the given bucket name, region and buf.
func UploadZipManager(bucketName, region, dir string, buf *bytes.Buffer) error {
	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(region),
		// Put the credentials here.
		// Credentials: credentials.NewStaticCredentials("ID", "Key", ""),
		LogLevel: aws.LogLevel(aws.LogDebugWithHTTPBody),
	})
	if err != nil {
		return err
	}

	svc := s3.New(sess)
	reader, err := zip.NewReader(bytes.NewReader(buf.Bytes()), int64(buf.Len()))
	if err != nil {
		return err
	}

	// Extract each file from the zip archive
	for _, file := range reader.File {
		// Open the file from the zip archive
		rc, err := file.Open()
		if err != nil {
			return err
		}
		defer rc.Close()

		// Create a buffer to store the file contents
		buffer := new(bytes.Buffer)
		if _, err := io.Copy(buffer, rc); err != nil {
			return err
		}

		objectKeyDir := filepath.Join("datasets", dir)
		objectKey := filepath.Join(objectKeyDir, file.Name)

		_, err = svc.PutObject(&s3.PutObjectInput{
			Bucket: aws.String(bucketName),
			Key:    aws.String(objectKey),
			Body:   bytes.NewReader(buffer.Bytes()),
		})
		if err != nil {
			return err
		}
	}

	return nil
}

func UploadTarManager(bucketName, region, dir string, buf *bytes.Buffer) error {
	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(region),
		// Put the credentials here.
		// Credentials: credentials.NewStaticCredentials("ID", "Key", ""),
		LogLevel: aws.LogLevel(aws.LogDebugWithHTTPBody),
	})
	if err != nil {
		return err
	}

	svc := s3.New(sess)
	tarReader := tar.NewReader(buf)

	// Extract each file from the tar archive
	for {
		header, err := tarReader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}

		// skip if the entry represents a directory
		if header.Typeflag == tar.TypeDir {
			continue
		}

		// Create a buffer to store the file contents
		buffer := new(bytes.Buffer)
		if _, err := io.Copy(buffer, tarReader); err != nil {
			return err
		}

		objectKeyDir := filepath.Join("datasets", dir)
		objectKey := filepath.Join(objectKeyDir, header.Name)

		_, err = svc.PutObject(&s3.PutObjectInput{
			Bucket: aws.String(bucketName),
			Key:    aws.String(objectKey),
			Body:   bytes.NewReader(buffer.Bytes()),
		})
		if err != nil {
			return err
		}
	}

	return nil
}

// ListManager lists all the buckets in the S3 bucket with the given bucket name, folder prefix and region.
func ListManager(bucketName, folderPrefix, region string) ([]string, error) {
	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(region),
		// Put the credentials here.
		// Credentials: credentials.NewStaticCredentials("ID", "Key", ""),
		LogLevel: aws.LogLevel(aws.LogDebugWithHTTPBody),
	})
	if err != nil {
		return nil, err
	}

	svc := s3.New(sess)

	result, err := svc.ListObjectsV2(&s3.ListObjectsV2Input{
		Bucket: aws.String(bucketName),
		Prefix: aws.String(folderPrefix),
	})

	if err != nil {
		return nil, err
	}

	name := []string{}
	for _, obj := range result.Contents {
		name = append(name, *obj.Key)
	}

	return name, nil
}

// Resize a specific node group by setting a different desiredSize
// The api server needs to have permission to the action eks:UpdateNodegroupConfig
func ResizeWorkerNodeGroup(clusterName, nodegroupName, region string, desiredSize int64) error {
	sess, err := session.NewSession(&aws.Config{Region: aws.String(region)})
	if err != nil {
		return err
	}

	client := eks.New(sess)

	inputConfig := eks.UpdateNodegroupConfigInput{
		ClusterName:   &clusterName,
		NodegroupName: &nodegroupName,
		ScalingConfig: &eks.NodegroupScalingConfig{
			DesiredSize: &desiredSize,
		},
	}
	_, err = client.UpdateNodegroupConfig(&inputConfig)
	if err != nil {
		return err
	}

	return nil
}

// Get the current nodegroup size
// The api server needs to have permission to the action eks:DescribeNodegroup
func GetNodeGroupSize(clusterName, nodegroupName, region string) (int64, error) {
	sess, err := session.NewSession(&aws.Config{Region: aws.String(region)})
	if err != nil {
		return 0, err
	}

	client := eks.New(sess)

	input := eks.DescribeNodegroupInput{
		ClusterName:   &clusterName,
		NodegroupName: &nodegroupName,
	}

	output, err := client.DescribeNodegroup(&input)
	if err != nil {
		return 0, err
	}

	return *output.Nodegroup.ScalingConfig.DesiredSize, nil
}
