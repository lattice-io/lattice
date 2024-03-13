// Derived from kubeflow/training-operator

package util

import (
	"fmt"
	"strings"
	"time"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	latticeconfig "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/config"
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	commonutil "github.com/kubeflow/common/pkg/util"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

const (
	getLatticeInstallerCmd  = "pip install lattice-installer -i https://${LATTICE_JFROG_USER}:${LATTICE_JFROG_KEY}@breezeml.jfrog.io/artifactory/api/pypi/breezeml-pypi/simple"
	latticeInstallerCmdBase = "python -m lattice_installer.install"
	latticeAgentCmd         = "python -m lattice.run"

	// Env names for lattice agent
	EnvLatticeJfrogUser   = "LATTICE_JFROG_USER"
	EnvLatticeJfrogKey    = "LATTICE_JFROG_KEY"
	EnvLatticeAgentRdzvId = "LATTICE_RDZV_ID"
	EnvLatticeAgentNNodes = "LATTICE_NNODES"
	EnvLatticeFramework   = "LATTICE_FRAMEWORK"

	EnvLatticeAddonsCheckpointType   = "LATTICE_CHECKPOINT_TYPE"
	EnvLatticeAddonsCheckpointConfig = "LATTICE_CHECKPOINT_CONFIG"
	EnvLatticeAddonsAutopatch        = "LATTICE_AUTOPATCH"

	EnvLatticeAgentRdzvBackend  = "LATTICE_RDZV_BACKEND"
	EnvLatticeAgentRdzvPort     = "LATTICE_RDZV_CLIENT_SERVICE_PORT"
	EnvLatticeAgentRdzvEndpoint = "LATTICE_RDZV_CLIENT_SERVICE_HOST"
)

type ObjectFilterFunction func(obj metav1.Object) bool

// ConvertServiceList convert service list to service point list
func ConvertServiceList(list []corev1.Service) []*corev1.Service {
	if list == nil {
		return nil
	}
	ret := make([]*corev1.Service, 0, len(list))
	for i := range list {
		ret = append(ret, &list[i])
	}
	return ret
}

// ConvertPodList convert pod list to pod pointer list
func ConvertPodList(list []corev1.Pod) []*corev1.Pod {
	if list == nil {
		return nil
	}
	ret := make([]*corev1.Pod, 0, len(list))
	for i := range list {
		ret = append(ret, &list[i])
	}
	return ret
}

// ConvertPodListWithFilter converts pod list to pod pointer list with ObjectFilterFunction
func ConvertPodListWithFilter(list []corev1.Pod, pass ObjectFilterFunction) []*corev1.Pod {
	if list == nil {
		return nil
	}
	ret := make([]*corev1.Pod, 0, len(list))
	for i := range list {
		obj := &list[i]
		if pass != nil {
			if pass(obj) {
				ret = append(ret, obj)
			}
		} else {
			ret = append(ret, obj)
		}
	}
	return ret
}

func GetReplicaTypes(specs map[commonv1.ReplicaType]*commonv1.ReplicaSpec) []commonv1.ReplicaType {
	keys := make([]commonv1.ReplicaType, 0, len(specs))
	for k := range specs {
		keys = append(keys, k)
	}
	return keys
}

// DurationUntilExpireTime returns the duration until job needs to be cleaned up, or -1 if it's infinite.
func DurationUntilExpireTime(runPolicy *commonv1.RunPolicy, jobStatus commonv1.JobStatus) (time.Duration, error) {
	if !commonutil.IsSucceeded(jobStatus) && !commonutil.IsFailed(jobStatus) {
		return -1, nil
	}
	currentTime := time.Now()
	ttl := runPolicy.TTLSecondsAfterFinished
	if ttl == nil {
		return -1, nil
	}
	duration := time.Second * time.Duration(*ttl)
	if jobStatus.CompletionTime == nil {
		return -1, fmt.Errorf("job completion time is nil, cannot cleanup")
	}
	finishTime := jobStatus.CompletionTime
	expireTime := finishTime.Add(duration)
	if currentTime.After(expireTime) {
		return 0, nil
	} else {
		return expireTime.Sub(currentTime), nil
	}
}

// Return if all pods are ready (not ContainerCreating or Terminating)
func AllPodsReady(pods []*corev1.Pod) bool {
	for _, pod := range pods {
		if pod.DeletionTimestamp != nil {
			return false
		}
		if pod.Status.Phase == corev1.PodPending {
			return false
		}
	}
	return true
}

// Return the number of running pods
func NumRunningPods(pods []*corev1.Pod) int32 {
	numRunning := 0
	for _, pod := range pods {
		if pod.Status.Phase == corev1.PodRunning && pod.DeletionTimestamp == nil {
			numRunning++
		}
	}
	return int32(numRunning)
}

func ModifyCommand(trainingjob *breezemlv1.TrainingJob, newCommand []string) []string {
	// Assume that there is only one application container (Containers[0])
	currentCmd := make([]string, len(trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Command))
	copy(currentCmd, trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Command)

	trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Command = newCommand

	// TODO: Consider some sanitization of original command as it may come in many different formats
	// For example: Command = ["python", "-m", "torch.distributed.run"] or
	// Command = ["python"], Args = ["-m", "torch.distributed.run"]
	// Both run the same thing but need to be handled differetly

	return currentCmd
}

func GetJobArgs(trainingjob *breezemlv1.TrainingJob) []string {
	// Assume that there is only one application container (Containers[0])
	currentArgs := make([]string, len(trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Args))
	copy(currentArgs, trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Args)

	return currentArgs
}

func ModifyArgs(trainingjob *breezemlv1.TrainingJob, newArgs []string) []string {
	currentArgs := GetJobArgs(trainingjob)

	trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Args = newArgs

	return currentArgs
}

func CreateFinalCommand(cmdList []string) []string {
	finalCmd := make([]string, 1)
	finalCmd[0] = strings.Join(cmdList, " && ")

	return finalCmd
}

func BuildLatticeWrapperCommand(framework *breezemlv1.TrainingJobFramework, originalCmd []string, originalArgs []string) []string {
	latticeWrapperCmds := []string{}
	// Prepend the installer commands -- pip install the installer and run it
	latticeWrapperCmds = append(latticeWrapperCmds, getLatticeInstallerCmd)
	latticeInstallerCmd := fmt.Sprintf("%s '%s' --framework %s", latticeInstallerCmdBase, strings.Join(originalCmd, " "), string(*framework))
	latticeWrapperCmds = append(latticeWrapperCmds, latticeInstallerCmd)

	// Prepend the Lattice Agent to the original entrypoint provided by the user
	wrappedCommand := latticeAgentCmd + " " + strings.Join(originalCmd, " ") + " " + strings.Join(originalArgs, " ")
	latticeWrapperCmds = append(latticeWrapperCmds, wrappedCommand)

	return latticeWrapperCmds
}

func AddAuthenticationEnvVars(trainingjob *breezemlv1.TrainingJob, jfrogSecret *latticeconfig.JFrogSecret) error {
	if jfrogSecret == nil {
		return fmt.Errorf("JFrog secret is nil. Perhaps the environment variable %s is not set?", OperatorEnvJFrogSecretPath)
	}

	// Instantiate two empty EnvVars with all memory initialized
	envList := make([]corev1.EnvVar, 2)

	// Create one variable for the JFROG username
	envList[0].Name = EnvLatticeJfrogUser
	envList[0].Value = jfrogSecret.Username

	// Create one variable for the JFROG password
	envList[1].Name = EnvLatticeJfrogKey
	envList[1].Value = jfrogSecret.Password

	envListRef := &trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Env
	*envListRef = append(*envListRef, envList...)

	return nil
}

func AddAgentConfigurationEnvVars(trainingjob *breezemlv1.TrainingJob, config *latticeconfig.LatticeConfig) {
	agentConfigEnvList := make([]corev1.EnvVar, 0)
	nNodesValue := fmt.Sprintf("%d:%d", *trainingjob.Spec.MinSize, *trainingjob.Spec.MaxSize)
	agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
		Name:  EnvLatticeAgentNNodes,
		Value: nNodesValue,
	})

	agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
		Name:  EnvLatticeAgentRdzvId,
		Value: string(trainingjob.UID),
	})

	agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
		Name:  EnvLatticeFramework,
		Value: string(*trainingjob.Spec.Framework),
	})

	if config.LatticeAgentRendezvousBackend != "" {
		agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
			Name:  EnvLatticeAgentRdzvBackend,
			Value: config.LatticeAgentRendezvousBackend,
		})
	}

	if config.LatticeAgentRendezvousEndpoint != "" {
		agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
			Name:  EnvLatticeAgentRdzvEndpoint,
			Value: config.LatticeAgentRendezvousEndpoint,
		})
	}

	if config.LatticeAgentRendezvousPort != "" {
		agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
			Name:  EnvLatticeAgentRdzvPort,
			Value: config.LatticeAgentRendezvousPort,
		})
	}

	latticeAddonsCheckpointType := config.LatticeAddonsCheckpointType
	if latticeAddonsCheckpointType == "" {
		latticeAddonsCheckpointType = "remote"
	}
	agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
		Name:  EnvLatticeAddonsCheckpointType,
		Value: latticeAddonsCheckpointType,
	})

	addonsBackendConfig := ""
	if latticeAddonsCheckpointType == "remote" {
		addonsBackendConfig = "job_id=" + string(trainingjob.UID)
		if config.LatticeAddonsCheckpointEndpoint != "" {
			addonsBackendConfig = addonsBackendConfig + fmt.Sprintf(",ckpt_service_endpoint=%s", config.LatticeAddonsCheckpointEndpoint)
		}

		if config.LatticeAddonsCheckpointPort != "" {
			addonsBackendConfig = addonsBackendConfig + fmt.Sprintf(",ckpt_service_port=%s", config.LatticeAddonsCheckpointPort)
		}
	} else if latticeAddonsCheckpointType == "local" {
		addonsBackendConfig = "root=/tmp/" + string(trainingjob.UID)
	}
	agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
		Name:  EnvLatticeAddonsCheckpointConfig,
		Value: addonsBackendConfig,
	})

	latticeAutopatchValue := ""
	if *trainingjob.Spec.Framework == "pytorch" {
		latticeAutopatchValue = "torch"
	}
	agentConfigEnvList = append(agentConfigEnvList, corev1.EnvVar{
		Name:  EnvLatticeAddonsAutopatch,
		Value: latticeAutopatchValue,
	})

	envListRef := &trainingjob.Spec.ReplicaSpecs.Template.Spec.Containers[0].Env
	*envListRef = append(*envListRef, agentConfigEnvList...)
}

// Prepend lattice-addons and lattice-agent install before
func WrapEntrypoint(trainingjob *breezemlv1.TrainingJob, config *latticeconfig.LatticeConfig) error {
	// Add all necessary env vars for the installer and the agent
	err := AddAuthenticationEnvVars(trainingjob, config.JFrogSecret)
	if err != nil {
		// If `JFROG_SECRET_NAME` is not set, we cannot continue
		// Don't modify it
		return err
	}
	AddAgentConfigurationEnvVars(trainingjob, config)

	// If we are wrapping with Lattice, set restartPolicy to Never
	// If Lattice install fails we don't want to just keep retrying
	trainingjob.Spec.ReplicaSpecs.RestartPolicy = "Never"

	// Replace the original command but return a reference to it
	originalCmds := ModifyCommand(trainingjob, []string{"/bin/bash", "-c"})
	originalArgs := GetJobArgs(trainingjob)

	latticeWrapperCmds := BuildLatticeWrapperCommand(trainingjob.Spec.Framework, originalCmds, originalArgs)

	// Combine the list into a final command and replace the args
	latticeCommands := CreateFinalCommand(latticeWrapperCmds)
	ModifyArgs(trainingjob, latticeCommands)

	return nil
}

// parse node selector raw values like
// {"0": "key0=value0", "1": "key1=value1"} into
// {key0: value0, key1: value1}
func parseNodeSelectors(rawData []string) client.MatchingLabels {
	result := make(client.MatchingLabels)
	for _, rawValue := range rawData {
		valueSlice := strings.Split(rawValue, "=")
		if len(valueSlice) < 2 {
			continue
		}
		result[valueSlice[0]] = strings.Join(valueSlice[1:], "")
	}
	return result
}

// Append jobNodeSelectors to actual trainingjobs
func WrapJobNodeSelector(trainingjob *breezemlv1.TrainingJob, labels *client.MatchingLabels) {
	for key, value := range *labels {
		// If the node selector doesn't exist, create it
		if trainingjob.Spec.ReplicaSpecs.Template.Spec.NodeSelector == nil {
			trainingjob.Spec.ReplicaSpecs.Template.Spec.NodeSelector = make(map[string]string)
		}

		if _, ok := trainingjob.Spec.ReplicaSpecs.Template.Spec.NodeSelector[key]; !ok {
			// if the key does not already exist in the job's node selector, append it
			// if it already exists, we respect user-specified value
			trainingjob.Spec.ReplicaSpecs.Template.Spec.NodeSelector[key] = value
		}
	}
}
