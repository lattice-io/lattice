package k8s

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"lattice-api-server/pkg/aws"
	"lattice-api-server/pkg/types"
	"lattice-api-server/pkg/util"
	"path/filepath"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
	"k8s.io/client-go/util/homedir"

	k8stypes "k8s.io/apimachinery/pkg/types"
)

// NAMESPACE as the input name of environment variable.
const (
	NAMESPACE             = "NAMESPACE"
	API_GROUP             = "API_GROUP"
	API_VERSION           = "API_VERSION"
	TRAININGJOB_S3URL_ENV = "S3URL"

	nodeGroupLabelKey = "eks.amazonaws.com/nodegroup"
)

// ConnectK8s When deploying the API server in a different k8s cluster, please set inCluster to false.
func ConnectK8s(inCluster bool) *kubernetes.Clientset {
	var err error
	var config *rest.Config

	if inCluster {
		config, err = rest.InClusterConfig()
	} else {
		var kubeconfig *string
		if home := homedir.HomeDir(); home != "" {
			kubeconfig = flag.String("kubeconfig", filepath.Join(home, ".kube", "config"), "(optional) absolute path to the kubeconfig file")
		} else {
			kubeconfig = flag.String("kubeconfig", "", "absolute path to the kubeconfig file")
		}
		flag.Parse()
		config, err = clientcmd.BuildConfigFromFlags("", *kubeconfig)
	}

	if err != nil {
		panic(err.Error())
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		panic(err.Error())
	}

	return clientset
}

// GetKubeJobs get the k8s jobs information.
func GetKubeJobs(clientSet *kubernetes.Clientset) ([]byte, error) {
	resourcePath := fmt.Sprintf("/apis/%s/%s/namespaces/%s/trainingjobs",
		util.GetEnv(API_GROUP), util.GetEnv(API_VERSION), util.GetEnv(NAMESPACE))
	data, err := clientSet.RESTClient().
		Get().
		AbsPath(resourcePath).
		DoRaw(context.TODO())

	return data, err
}

// GetKubeJob get the k8s job information.
func GetKubeJob(clientSet *kubernetes.Clientset, namespace string, jobName string) ([]byte, error) {
	resourcePath := fmt.Sprintf("/apis/%s/%s/namespaces/%s/trainingjobs/%s",
		util.GetEnv(API_GROUP), util.GetEnv(API_VERSION), namespace, jobName)
	data, err := clientSet.RESTClient().
		Get().
		AbsPath(resourcePath).
		DoRaw(context.TODO())

	return data, err
}

// applyS3Bucket adds s3 service account and endpoint to the job
func applyS3Bucket(job *types.TrainingJob, endpoint string) error {
	job.Spec.ReplicaSpecs.Template.Spec.ServiceAccountName = GetS3ServiceAccount()
	if len(job.Spec.ReplicaSpecs.Template.Spec.Containers) != 1 {
		return fmt.Errorf("the number of containers for each pod should be 1 in %s", job.Name)
	}
	s3EnvVar := v1.EnvVar{
		Name:  TRAININGJOB_S3URL_ENV,
		Value: endpoint,
	}
	job.Spec.ReplicaSpecs.Template.Spec.Containers[0].Env = append(job.Spec.ReplicaSpecs.Template.Spec.Containers[0].Env, s3EnvVar)
	return nil
}

// CreateKubeJob create a new kubernetes job.
func CreateKubeJob(clientSet *kubernetes.Clientset, newJob types.TrainingJob) error {
	// apply s3 information to generate model downloading link
	s3Endpoint := aws.GenerateS3Endpoint(&newJob, aws.GetAWSS3Bucket())
	if err := applyS3Bucket(&newJob, s3Endpoint); err != nil {
		return err
	}

	body, err := json.Marshal(newJob)
	if err != nil {
		return err
	}

	resourcePath := fmt.Sprintf("/apis/%s/namespaces/%s/%s", newJob.APIVersion, newJob.Namespace, types.TrainingJobPlural)
	_, err = clientSet.RESTClient().
		Post().
		AbsPath(resourcePath).
		Body(body).
		DoRaw(context.TODO())

	return err
}

// UpdateKubeJob update an existing kubernetes job.
func UpdateKubeJobPriority(clientSet *kubernetes.Clientset, newJob types.JobPriorityPatch) error {
	mergePatch, err := json.Marshal(newJob)
	if err != nil {
		return err
	}

	resourcePath := fmt.Sprintf("/apis/%s/namespaces/%s/%s/%s", newJob.APIVersion, newJob.Namespace, types.TrainingJobPlural, newJob.Name)
	_, err = clientSet.RESTClient().
		Patch(k8stypes.MergePatchType).
		AbsPath(resourcePath).
		Body(mergePatch).
		DoRaw(context.TODO())

	return err
}

// DeleteKubeJobs delete a k8s job.
func DeleteKubeJobs(clientSet *kubernetes.Clientset, jobName string) error {
	resourcePath := fmt.Sprintf("/apis/%s/%s/namespaces/%s/trainingjobs/%s",
		util.GetEnv(API_GROUP), util.GetEnv(API_VERSION), util.GetEnv(NAMESPACE), jobName)

	_, err := clientSet.RESTClient().
		Delete().
		AbsPath(resourcePath).
		DoRaw(context.TODO())

	return err
}

// Get Job placement information
func GetJobPlacement(clientSet *kubernetes.Clientset, nodeGroup string) (types.JobPlacement, error) {
	// list all pods in the namespace whose Status.Phase is "Running"
	pods, err := clientSet.CoreV1().
		Pods(util.GetEnv(NAMESPACE)).
		List(context.TODO(), metav1.ListOptions{FieldSelector: "status.phase=Running"})
	if err != nil {
		return nil, err
	}

	// list all nodes with the label "eks.amazonaws.com/nodegroup=<nodeGroup>"
	nodes, err := clientSet.CoreV1().
		Nodes().
		List(context.TODO(), metav1.ListOptions{LabelSelector: fmt.Sprintf("%s=%s", nodeGroupLabelKey, nodeGroup)})
	if err != nil {
		return nil, err
	}

	// Initialize the placement map
	placement := make(types.JobPlacement)
	for _, node := range nodes.Items {
		placement[node.Name] = []string{}
	}

	// Go through all pods, and update the placement map
	for _, pod := range pods.Items {
		if pod.Status.Phase == v1.PodRunning {
			// Check if the pod has a label "job-name"
			if job_name, ok := pod.Labels["training.kubeflow.org/job-name"]; ok {
				if len(pod.Spec.NodeName) > 0 {
					placement[pod.Spec.NodeName] = append(placement[pod.Spec.NodeName], job_name)
				}
			}
		}
	}

	return placement, nil
}

// Get the number of actually-running pods for a job
func GetRunningSize(jobUID string, placement types.JobPlacement) int32 {
	size := int32(0)
	for _, jobs := range placement {
		for _, job := range jobs {
			if job == jobUID {
				size++
			}
		}
	}
	return size
}
