package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"lattice-api-server/pkg/aws"
	"lattice-api-server/pkg/k8s"
	"lattice-api-server/pkg/loki"
	"lattice-api-server/pkg/prometheus"
	"lattice-api-server/pkg/types"
	"path/filepath"

	// "mime/multipart"
	"net/http"
	"os"
	"sort"
	"time"

	"github.com/gin-gonic/gin"
	cors "github.com/rs/cors/wrapper/gin"
)

const (
	inClusterEnv  = "IN_CLUSTER"
	portNumberEnv = "PORT_NUMBER"
	awsRegion     = "AWS_REGION"
	awsS3Bucket   = "AWS_S3_BUCKET"
)

var clientSet = k8s.ConnectK8s(getInClusterInfo())
var portNumber = getPortNumber()

// postJob adds a job from JSON received in the request body.
func postJob(c *gin.Context) {
	var newJob types.TrainingJob
	if err := c.BindJSON(&newJob); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	err := k8s.CreateKubeJob(clientSet, newJob)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	} else {
		c.JSON(http.StatusCreated, newJob)
	}
}

// postBert adds a bert job from JSON received in the request body.
// It only uses the metadata received from JSON, but replace the spec field
// with a pre-defined template TrainingJobSpec.
func postBert(c *gin.Context) {
	var jobWrapper types.TrainingJobExampleWrapper
	if err := c.BindJSON(&jobWrapper); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Copy job meta (name, namespace, etc.) from job wrapper
	var newJob types.TrainingJob
	newJob.TypeMeta = jobWrapper.TypeMeta
	newJob.ObjectMeta = jobWrapper.ObjectMeta
	newJob.Spec = *k8s.ExampleBertSpec.DeepCopy()

	// If the number of epochs is set, add it to the arg s
	if jobWrapper.Epochs != nil {
		if err := k8s.AddMaxEpochs(&newJob, *jobWrapper.Epochs, "--max_epochs"); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		}
	}

	err := k8s.CreateKubeJob(clientSet, newJob)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	} else {
		c.JSON(http.StatusCreated, newJob)
	}
}

// postResnet adds a resnet job from JSON received in the request body.
// It only uses the metadata received from JSON, but replace the spec field
// with a pre-defined template TrainingJobSpec.
func postResnet(c *gin.Context) {
	var jobWrapper types.TrainingJobExampleWrapper
	if err := c.BindJSON(&jobWrapper); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Copy job meta (name, namespace, etc.) from job wrapper
	var newJob types.TrainingJob
	newJob.TypeMeta = jobWrapper.TypeMeta
	newJob.ObjectMeta = jobWrapper.ObjectMeta
	newJob.Spec = *k8s.ExampleResnetSpec.DeepCopy()

	// If the number of epochs is set, add it to the args
	if jobWrapper.Epochs != nil {
		if err := k8s.AddMaxEpochs(&newJob, *jobWrapper.Epochs, "--max-epochs"); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		}
	}

	err := k8s.CreateKubeJob(clientSet, newJob)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	} else {
		c.JSON(http.StatusCreated, newJob)
	}
}

// updateJob updates a job from JSON received in the request body.
// it uses the same logic as postJob
func updateJob(c *gin.Context) {
	jsonData, err := c.GetRawData()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var priorityPatch types.JobPriorityPatch
	if err := json.Unmarshal(jsonData, &priorityPatch); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	err = k8s.UpdateKubeJobPriority(clientSet, priorityPatch)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	} else {
		var response map[string]interface{}
		if err := json.Unmarshal(jsonData, &response); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		} else {
			c.JSON(http.StatusAccepted, priorityPatch)
		}
	}
}

// deleteJobs delete a training job on Lattice.
func deleteJobs(c *gin.Context) {
	targetName := c.Query("name")
	err := k8s.DeleteKubeJobs(clientSet, targetName)

	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "success"})
}

// getJobs responds with the list of all Jobs as JSON.
func getJobs(c *gin.Context) {
	var jobList []types.Job
	var k8sJobList types.TrainingJobList

	jobData, k8sErr := k8s.GetKubeJobs(clientSet)
	if k8sErr != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": k8sErr.Error()})
		return
	}

	jsonErr := json.Unmarshal(jobData, &k8sJobList)
	if jsonErr != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": jsonErr.Error()})
		return
	}

	// Sort the job list by submit time
	sort.Slice(k8sJobList.Items, func(i, j int) bool {
		return k8sJobList.Items[i].Status.SubmitTime.Before(k8sJobList.Items[j].Status.SubmitTime)
	})

	// Get the map between job names and job uids
	jobNameToUIDMap := k8sJobList.GetJobNameToUidMap()

	// We don't handle error for prometheus in a hard way
	// If we encounter an error, we give an empty time series
	timeSeries, prometheusErr := prometheus.FetchTimeSeries(jobNameToUIDMap)
	if prometheusErr != nil {
		timeSeries = make(prometheus.TimeSeries)
	}

	// Get the job placement in nodes
	nodeGroup := aws.GetAWSEKSWorkerNodegroup()
	placement, placementErr := k8s.GetJobPlacement(clientSet, nodeGroup)
	if placementErr != nil {
		placement = make(types.JobPlacement)
	} else {
		// Replace job names with job IDs
		for node := range placement {
			for i := range placement[node] {
				if _, ok := jobNameToUIDMap[placement[node][i]]; ok {
					placement[node][i] = jobNameToUIDMap[placement[node][i]]
				}
			}
		}
	}

	for _, job := range k8sJobList.Items {
		// Calculate the job running time.
		var jobStartTimeMsg string
		if job.Status.LastExecTime != nil {
			jobStartTimeMsg = job.Status.LastExecTime.String()
		} else {
			jobStartTimeMsg = "Waiting"
		}

		var runningTimeMsg string
		if job.Status.Stage == types.TrainingJobStageRunning {
			runningTimeMsg = time.Since(job.Status.LastExecTime.Time).String()
		} else if job.Status.Stage == types.TrainingJobStageWaiting {
			runningTimeMsg = "Waiting"
		} else if job.Status.Stage == types.TrainingJobStageCompleted {
			runningTimeMsg = job.Status.CompletionTime.Sub(job.Status.LastExecTime.Time).String()
		} else {
			runningTimeMsg = ""
		}

		// get the job priority
		// it is by default 0
		jobPriority := int32(0)
		if job.Spec.Priority != nil {
			jobPriority = *job.Spec.Priority
		}

		// generate the AWS S3 pre-signed URL for getting an object (for downloading completed training model weights).
		// the S3 file object key is job's name with .zip format.
		preSignedURL, err := aws.GeneratePresignedURL(aws.GetAWSS3Bucket(), job.Name+".zip", aws.GetAWSRegion(), aws.DAY)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"generating AWS pre-signed URL error:": err.Error()})
			return
		}

		// get the job's size history (time series)
		sizeHistory := make([]prometheus.PrometheusValue, 0)
		if val, ok := timeSeries[string(job.UID)]; ok {
			jobSubmitTime := float64(job.Status.SubmitTime.Unix())
			sizeHistory = prometheus.FilterTimeSeries(&val, jobSubmitTime)
		}

		jobUID := fmt.Sprintf("%v", job.UID)

		// get the job's current running size
		runningSize := k8s.GetRunningSize(jobUID, placement)

		// Create the new job list for front-end.
		jobList = append(jobList, types.Job{
			ID:          jobUID,
			Name:        job.Name,
			Namespace:   job.Namespace,
			Experiment:  "Example Exp",
			User:        "",
			Status:      fmt.Sprintf("%v", job.Status.Stage),
			StartTime:   jobStartTimeMsg,
			RunningTime: runningTimeMsg,
			CurrentSize: job.Status.CurrentSize,
			RunningSize: runningSize,
			DownloadURL: preSignedURL,
			Priority:    jobPriority,
			CPUs:        128,
			GPUs:        8,
			Memory:      1024,
			SizeHistory: sizeHistory,
		})
	}

	// Generate the response
	response := types.GetJobResponse{
		Jobs:      jobList,
		Placement: placement,
	}

	c.JSON(http.StatusOK, response)
}

// getLog returns the log of a job
func getLog(c *gin.Context) {
	jobName := c.Param("jobId")
	namespace := c.Param("namespace")

	// Get the job
	var job types.TrainingJob
	jobData, k8sErr := k8s.GetKubeJob(clientSet, namespace, jobName)
	if k8sErr != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": k8sErr.Error()})
		return
	}

	jsonErr := json.Unmarshal(jobData, &job)
	if jsonErr != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": jsonErr.Error()})
		return
	}

	lokiLog, err := loki.FetchLokiLogs(&job)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Generate the response
	response := loki.LokiLogResponse{
		Log: lokiLog,
	}

	c.JSON(http.StatusOK, response)
}

// scaleCluster resizes the size of the worker node group
func scaleCluster(c *gin.Context) {
	var resizePatch types.ClusterResizePatch
	if err := c.BindJSON(&resizePatch); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	maxClusterSize := aws.GetMaxClusterSize()
	if resizePatch.DesiredSize > maxClusterSize {
		c.JSON(http.StatusBadRequest, gin.H{"error": fmt.Sprintf("The desired size is larger than the maximum cluster size: %d", maxClusterSize)})
		return
	}

	cluster := aws.GetAWSEKSClusterName()
	nodeGroup := aws.GetAWSEKSWorkerNodegroup()
	region := aws.GetAWSRegion()

	err := aws.ResizeWorkerNodeGroup(cluster, nodeGroup, region, resizePatch.DesiredSize)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	} else {
		c.JSON(http.StatusAccepted, resizePatch)
	}
}

// clusterSize get the size of the current worker node group
func clusterSize(c *gin.Context) {
	cluster := aws.GetAWSEKSClusterName()
	nodeGroup := aws.GetAWSEKSWorkerNodegroup()
	region := aws.GetAWSRegion()

	clusterSize, err := aws.GetNodeGroupSize(cluster, nodeGroup, region)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	} else {
		c.JSON(http.StatusAccepted, types.ClusterResizePatch{
			DesiredSize: clusterSize,
		})
	}
}

// listDatasets list datasets in S3 datasets folder
func listDatasets(c *gin.Context) {
	datasets, err := aws.ListManager(aws.GetAWSS3Bucket(), "datasets/", aws.GetAWSRegion())
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var datasetList []types.Dataset
	for _, obj := range datasets {
		datasetList = append(datasetList, types.Dataset{
			Name:     obj,
			Location: aws.GetAWSS3Bucket(),
		})
	}

	c.JSON(http.StatusOK, datasetList)
}

// uploadDatasets uploads datasets to S3 datasets folder
func uploadDatasets(c *gin.Context) {
	formFile, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	src, err := formFile.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	defer src.Close()

	// Determine the file extension (zip or tar)
	fileExt := filepath.Ext(formFile.Filename)
	if fileExt != ".zip" && fileExt != ".tar" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "file extension must be .zip or .tar"})
		return
	}

	// Read the file contents into a buffer
	buf := new(bytes.Buffer)
	_, err = io.Copy(buf, src)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	switch fileExt {
	case ".zip":
		err = aws.UploadZipManager(aws.GetAWSS3Bucket(), aws.GetAWSRegion(), formFile.Filename, buf)
	case ".tar":
		err = aws.UploadTarManager(aws.GetAWSS3Bucket(), aws.GetAWSRegion(), formFile.Filename, buf)
	}
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": "zip/tar files uploaded successfully"})
}

// downloadDatasets generate a AWS S3 pre-signed URL for downloading a dataset from S3 datasets folder
func downloadDatasets(c *gin.Context) {
	datasetName := c.Param("dataset_name")
	preSignedURL, err := aws.GeneratePresignedURL(aws.GetAWSS3Bucket(), "datasets/"+datasetName, aws.GetAWSRegion(), aws.DAY)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"generating AWS pre-signed URL error:": err.Error()})
		return
	}

	c.JSON(http.StatusOK, preSignedURL)
}

// get if we are in cluster
// if not, we should explicitly set IN_CLUSTER=false
func getInClusterInfo() bool {
	if envValue, ok := os.LookupEnv(inClusterEnv); ok {
		return !(envValue == "false")
	} else {
		return true
	}
}

// get the port number from the environment variables
// by default 8080
func getPortNumber() string {
	if envValue, ok := os.LookupEnv(portNumberEnv); ok {
		return envValue
	} else {
		return "8080"
	}
}

// main Gateways
func main() {
	router := gin.Default()
	router.Use(cors.AllowAll()) // Allow patch and other methods.

	// Health probe
	router.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{})
	})

	api := router.Group("/api")

	api.GET("/job", getJobs)
	api.POST("/job", postJob)
	api.DELETE("/job", deleteJobs)
	api.PATCH("/job", updateJob)
	api.GET("/log/:namespace/:jobId", getLog)
	api.POST("/job/resnet", postResnet)
	api.POST("/job/bert", postBert)

	api.POST("/cluster", scaleCluster)
	api.GET("/cluster", clusterSize)

	api.GET("/datasets", listDatasets)
	api.POST("/datasets", uploadDatasets)
	api.GET("/datasets/:dataset_name", downloadDatasets)

	endpoint := fmt.Sprintf("0.0.0.0:%s", portNumber)
	err := router.Run(endpoint)
	if err != nil {
		return
	}
}
