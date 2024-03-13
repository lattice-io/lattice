// Utilities for autoscaling

package util

import (
	"fmt"
	"sort"
	"time"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	trainingoperatorcommon "github.com/breezeml/lattice-operator/pkg/controller/breezeml.ai/v1/common"

	"github.com/go-logr/logr"
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	commonutil "github.com/kubeflow/common/pkg/util"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

const (
	NodeResourceType      string = "node"
	NvidiaGPUResourceType string = "nvidia.com/gpu"
)

// From a list of trainingjobs (fetched from cluster),
// we construct a job priority list based on their priority
// and queueTime
func ConstructPriorityList(
	jobs *breezemlv1.TrainingJobList,
	priorityList *[]*breezemlv1.TrainingJob,
	totalNumResources int32,
) error {
	returnError := false
	var err error

	// Empty the slice
	*priorityList = nil

	for i := range jobs.Items {
		job := &jobs.Items[i]

		// we need doing nothing for completed jobs
		if job.Status.Stage == breezemlv1.TrainingJobStageInit {
			err = fmt.Errorf("%s shouldn't be at init stage by this time. Check why it is not sent to waiting list", job.Name)
		} else if job.Status.Stage == breezemlv1.TrainingJobStageWaiting || job.Status.Stage == breezemlv1.TrainingJobStageRunning {
			*priorityList = append(*priorityList, job)
		}
	}

	// Sort the list based on jobs' Priority and QueuedTime
	sort.Slice(*priorityList, func(i, j int) bool {
		if *(*priorityList)[i].Spec.Priority != *(*priorityList)[j].Spec.Priority {
			return *(*priorityList)[i].Spec.Priority > *(*priorityList)[j].Spec.Priority
		} else {
			return (*priorityList)[i].Status.QueuedTime.Before((*priorityList)[j].Status.QueuedTime)
		}
	})

	if returnError {
		return err
	} else {
		return nil
	}
}

// We assign workers to our jobs.
// We go through all jobs based on their priority,
// and assign workers (resources) to them until we run out of resources
func DispatchWorkers(
	priorityList *[]*breezemlv1.TrainingJob,
	totalNumResources int32,
	resourceName corev1.ResourceName,
) error {
	returnError := false
	var err error

	remainingResources := totalNumResources
	finished := false // tracking whether we have stopped dispatching workers
	for i := range *priorityList {
		job := (*priorityList)[i]
		jobResourceUsage := ResourceUsagePerPod(job, resourceName)

		// If return an error if the intended size of the job is bigger than our whole cluster
		if *job.Spec.MinSize*jobResourceUsage > totalNumResources {
			returnError = true
			err = fmt.Errorf("the job %s needs more resource than we have in the cluster ", job.Name)
		}

		if finished {
			// We have stopped dispatching jobs.
			// Even if this job could fit in, we would not schedule it because
			// we want to keep a simple and strict priority-submissionTime order
			PauseJob(job)
		} else {
			if remainingResources >= *job.Spec.MaxSize*jobResourceUsage {
				// run the job with max size
				ResizeJob(job, *job.Spec.MaxSize)
				remainingResources -= (*job.Spec.MaxSize) * jobResourceUsage
			} else if remainingResources >= *job.Spec.MinSize*jobResourceUsage {
				// run the job with the remaining resources
				numWorkers := remainingResources / jobResourceUsage
				ResizeJob(job, numWorkers)
				remainingResources -= numWorkers * jobResourceUsage
			} else {
				// we could not run the job, we should stop scheduling jobs
				finished = true
				PauseJob(job)
			}
		}
	}

	if returnError {
		return err
	} else {
		return nil
	}
}

// From a list of trainingjobs (fetched from cluster),
// we construct running list and waiting list for the autoscaler
func ConstructSchedulingLists(
	priorityList *[]*breezemlv1.TrainingJob,
	runningList *[]*breezemlv1.TrainingJob,
	waitingList *[]*breezemlv1.TrainingJob,
	totalNumResources int32,
) error {
	for _, job := range *priorityList {
		if job.Status.Stage == breezemlv1.TrainingJobStageRunning {
			*runningList = append(*runningList, job)
		} else if job.Status.Stage == breezemlv1.TrainingJobStageWaiting {
			*waitingList = append(*waitingList, job)
		} else {
			return fmt.Errorf("the job %s has a wrong stage %s, should be Running or Waiting. ", job.Name, job.Status.Stage)
		}
	}
	return nil
}

// Return if job has ONLY been created and the timestamp
func JobIsOnlyCreated(status commonv1.JobStatus) (bool, metav1.Time) {
	if len(status.Conditions) > 1 {
		return false, metav1.Now()
	} else {
		if len(status.Conditions) == 1 {
			onlyCreated := status.Conditions[0].Type == commonv1.JobCreated && status.Conditions[0].Status == corev1.ConditionTrue
			return onlyCreated, metav1.Now()
		} else {
			return false, metav1.Now()
		}
	}
}

// Get the single-worker resource usage of a job
// Resource is reporesented with int32
// The resource usage of job is set at job.spec.replicaSpecs.template.spec.containers[x].resources.requests
// If unset or resourceName is not in its requests, return 1
// If ResourceName is "node", return 1
func ResourceUsagePerPod(job *breezemlv1.TrainingJob, resourceName corev1.ResourceName) int32 {
	if resourceName == corev1.ResourceName(NodeResourceType) {
		return int32(1)
	} else {
		resUsage := int32(0)
		for _, container := range job.Spec.ReplicaSpecs.Template.Spec.Containers {
			res := container.Resources.Requests.Name(resourceName, resource.DecimalSI)
			if val, ok := res.AsInt64(); ok {
				resUsage += int32(val)
			}
		}
		if resUsage == int32(0) {
			// This means that "resourceName" is unset in the job
			// By default, we set it to 1
			resUsage = int32(1)
		}
		return resUsage
	}
}

// Check if the TrainingJob is valid
func CheckConfiguration(job *breezemlv1.TrainingJob) error {
	if job.Spec.MinSize == nil {
		return fmt.Errorf("the job %s does not have minSize set", job.Name)
	}
	if job.Spec.MaxSize == nil {
		return fmt.Errorf("the job %s does not have maxSize set", job.Name)
	}

	if *job.Spec.MinSize < 1 {
		return fmt.Errorf("the job %s has minSize < 1", job.Name)
	}

	if *job.Spec.MinSize > *job.Spec.MaxSize {
		return fmt.Errorf("the job %s has minSize > maxSize", job.Name)
	}
	return nil
}

// Based on the real status (job.Status.ExecStatus.Conditions),
// mark the completed jobs to "Completed", and new jobs to "Waiting"
func ResetJobStatus(jobs *breezemlv1.TrainingJobList) error {
	var err error
	err = nil

	for idx := range jobs.Items {
		job := &jobs.Items[idx]

		// If job is invalid, we mark it as "Wrong"
		if err = CheckConfiguration(job); err != nil {
			WrongJob(job)
			continue
		}

		// In case the reconciler didn't take care of job completion, the autoscaler should
		// mark it as completed so that eventually it is removed from the running list,
		// preventing the job from holding the resources
		if commonutil.IsSucceeded(job.Status.ExecStatus) || commonutil.IsFailed(job.Status.ExecStatus) {
			// the job actually completed, we need to change the ideal status to completed
			// it should already be running or completed
			switch job.Status.Stage {
			case breezemlv1.TrainingJobStageRunning:
				CompleteJob(job)
			case breezemlv1.TrainingJobStageCompleted:
			default:
				err = fmt.Errorf("%s completed without running", job.Name)
			}
		}

		// If the job is just created or just becomes correct, we mark it as "Waiting"
		if job.Status.Stage == breezemlv1.TrainingJobStageInit || job.Status.Stage == breezemlv1.TrainingJobStageWrong {
			onlyCreated, time := JobIsOnlyCreated(job.Status.ExecStatus)
			job.Status.SubmitTime = &time
			QueueJob(job)
			if !onlyCreated {
				err = fmt.Errorf("%s seems not correctly configured during creation. Will put it into the waiting list anyway. ", job.Name)
			}
		}

		// If the job is on cooldown, we check whether it is out of the time out.
		if job.Status.Stage == breezemlv1.TrainingJobStageRequeuing {
			// If it's after the cooldown time range, we requeue the job into the waiting list.
			if job.Status.CooldownTime == nil {
				err = fmt.Errorf("%s is under cooldown without a due time ", job.Name)
			} else {
				if time.Now().After(job.Status.CooldownTime.Time) {
					// the job is requeued. We need to reset the timestamp
					QueueJob(job)
				}
			}
		}
	}

	return err
}

// Put the job into the waiting list
func QueueJob(job *breezemlv1.TrainingJob) {
	time := metav1.Now()
	job.Status.Stage = breezemlv1.TrainingJobStageWaiting
	job.Status.CurrentSize = 0
	job.Status.QueuedTime = &time
}

// Start a job, setting up the stage and timestamps
func StartJob(job *breezemlv1.TrainingJob, size int32) {
	time := metav1.Now()
	job.Status.Stage = breezemlv1.TrainingJobStageRunning
	job.Status.CurrentSize = size
	job.Status.LastExecTime = &time
}

// Complete a job, setting up the stage and timestamps
func CompleteJob(job *breezemlv1.TrainingJob) {
	time := metav1.Now()
	job.Status.Stage = breezemlv1.TrainingJobStageCompleted
	job.Status.CurrentSize = 0
	job.Status.CompletionTime = &time
}

// Requeue a job, setting up the stage and cooldown timestamp
func RequeueJob(job *breezemlv1.TrainingJob, cooldownTime *metav1.Time) {
	job.Status.Stage = breezemlv1.TrainingJobStageRequeuing
	job.Status.CurrentSize = 0
	job.Status.CooldownTime = cooldownTime
}

// Resize a job
func ResizeJob(job *breezemlv1.TrainingJob, size int32) {
	if job.Status.Stage == breezemlv1.TrainingJobStageWaiting {
		// start the job, need to set some extra fields
		time := metav1.Now()
		job.Status.Stage = breezemlv1.TrainingJobStageRunning
		job.Status.LastExecTime = &time
	}
	job.Status.CurrentSize = size
}

// Pause a job
func PauseJob(job *breezemlv1.TrainingJob) {
	job.Status.Stage = breezemlv1.TrainingJobStageWaiting
	job.Status.CurrentSize = 0
}

// Mark a job as wrong
func WrongJob(job *breezemlv1.TrainingJob) {
	job.Status.Stage = breezemlv1.TrainingJobStageWrong
	job.Status.CurrentSize = 0
}

// Find out how many pieces of resources (e.g., GPU) are idle
func GetIdleSize(
	runningList *[]*breezemlv1.TrainingJob,
	totalNumResources int32,
	resourceName corev1.ResourceName,
) int32 {
	// calculate the number of resource units used
	currentResourceUnit := int32(0)
	for _, job := range *runningList {
		currentResourceUnit += job.Status.CurrentSize * ResourceUsagePerPod(job, resourceName)
	}

	// keep track of the number of idle workers
	return totalNumResources - currentResourceUnit
}

// Check how many pieces of resources (e.g., GPU) we can seize from the running list
func calcNumResourcesToSeize(
	runningList *[]*breezemlv1.TrainingJob,
	priority int32,
	resourceName corev1.ResourceName,
) int32 {
	resourcesToSeize := int32(0)
	for _, job := range *runningList {
		jobResourceUsage := ResourceUsagePerPod(job, resourceName)
		if *job.Spec.Priority <= priority {
			resourcesToSeize += (job.Status.CurrentSize - *job.Spec.MinSize) * jobResourceUsage
		}
	}
	return resourcesToSeize
}

// Try to squeeze the first job in the waiting list into the running list
// We allow the job to seize workers from jobs in the running list with equal or lower priority.
// This function modifies runningList and waitingList in place.
// Return whether the operation is successful.
func squeezeFirstJob(
	runningList *[]*breezemlv1.TrainingJob,
	waitingList *[]*breezemlv1.TrainingJob,
	totalNumResources int32,
	resourceName corev1.ResourceName,
) bool {
	// If we don't have any job waiting, we consider it a failure
	if len(*waitingList) == 0 {
		return false
	}

	job := (*waitingList)[0] // the job to be started
	idleSize := GetIdleSize(runningList, totalNumResources, resourceName)
	jobResourceUsage := ResourceUsagePerPod(job, resourceName)

	// Case 1: we can start the job without seizing any workers
	if idleSize >= (*job.Spec.MinSize)*jobResourceUsage {
		// Find the number of workers
		numWorker := idleSize / jobResourceUsage
		if numWorker > *job.Spec.MaxSize {
			numWorker = *job.Spec.MaxSize
		}

		// Start the job and update the running and waiting lists
		StartJob(job, numWorker)
		*runningList = append(*runningList, job)
		*waitingList = (*waitingList)[1:]
		return true
	}

	// Find out how many workers we can seize from running jobs
	potentialResourcesToSeize := calcNumResourcesToSeize(runningList, *job.Spec.Priority, resourceName)

	// Case 2: we will need to seize some workers from running jobs
	if idleSize+potentialResourcesToSeize >= (*job.Spec.MinSize)*jobResourceUsage {
		// since we guarantee that the running list is sorted based on priority and there are enough resources to seize,
		// we don't need to consider priority in the logic. It is guaranteed that we will seize enough resources before
		// we reach a job with a higher priority.
		idxJobToSeize := len(*runningList) - 1 // index of the next job to seize
		numResourcesSeized := int32(0)
		for idxJobToSeize >= 0 && numResourcesSeized+idleSize < (*job.Spec.MinSize)*jobResourceUsage {
			jobRunning := (*runningList)[idxJobToSeize]
			jobRunningResourceUsage := ResourceUsagePerPod(jobRunning, resourceName)
			resourceNeeded := (*job.Spec.MinSize)*jobResourceUsage - numResourcesSeized - idleSize
			if (jobRunning.Status.CurrentSize-*jobRunning.Spec.MinSize)*jobRunningResourceUsage >= resourceNeeded {
				// this job already has enough resources we need
				workerToStop := (resourceNeeded + jobRunningResourceUsage - 1) / jobRunningResourceUsage
				numResourcesSeized += workerToStop * jobRunningResourceUsage
				ResizeJob(jobRunning, jobRunning.Status.CurrentSize-workerToStop)
				break
			} else {
				// this job is not enough
				workerToStop := jobRunning.Status.CurrentSize - *jobRunning.Spec.MinSize
				numResourcesSeized += workerToStop * jobRunningResourceUsage
				ResizeJob(jobRunning, jobRunning.Status.CurrentSize-workerToStop)
				idxJobToSeize--
			}
		}
		// we finish seizing workers. now we can start the job
		numWorker := (idleSize + numResourcesSeized) / jobResourceUsage
		StartJob(job, numWorker)
		*runningList = append(*runningList, job)
		*waitingList = (*waitingList)[1:]
		return true
	}

	// Case 3: we are not able to start the first job from the waiting list
	return false
}

// Try to start waiting jobs to take the remaining idle workers
func StartWaitingJobs(
	runningList *[]*breezemlv1.TrainingJob,
	waitingList *[]*breezemlv1.TrainingJob,
	totalNumResources int32,
	resourceName corev1.ResourceName,
	logger *logr.Logger,
) error {
	// Log how many jobs are running originally
	oldRunningCount := len(*runningList)

	// We repeatly try to squeeze the first job in the waiting list
	// into the running list until we fail
	for GetIdleSize(runningList, totalNumResources, resourceName) > 0 {
		succeeded := squeezeFirstJob(runningList, waitingList, totalNumResources, resourceName)

		// We always keep a strict order based on (priority, -queueTime) for runningList + waitingList.
		// No job can start before other jobs with higher (priority, -queueTime) are all started.
		// Therefore, if we reach a squeezing failure, we will terminate the squeezing process
		if !succeeded {
			break
		}
	}

	// Report how many jobs we have started
	newRunningCount := len(*runningList)
	idleSize := GetIdleSize(runningList, totalNumResources, resourceName)
	if logger != nil {
		logger.Info("Trying to start new jobs in the waiting list", "count", newRunningCount-oldRunningCount, "remainingIdleWorker", idleSize)
	}

	return nil
}

// check if we autoscaled a job
func TrainingJobAutoscaled(oldJob *breezemlv1.TrainingJob, newJob *breezemlv1.TrainingJob) bool {
	return !(oldJob.Status.Stage == newJob.Status.Stage && oldJob.Status.CurrentSize == newJob.Status.CurrentSize)
}

// check if we autoscaled any job in the list
func TrainingJobListAutoscaled(oldJobs *breezemlv1.TrainingJobList, newJobs *breezemlv1.TrainingJobList) bool {
	if len(oldJobs.Items) != len(newJobs.Items) {
		return true
	}

	for i := range oldJobs.Items {
		if TrainingJobAutoscaled(&oldJobs.Items[i], &newJobs.Items[i]) {
			return true
		}
	}

	return false
}

// If any job is on cooldown, we schedule a rerun for it
// If there are multiple jobs on cooldown, use the nearest due time
func FindRerunTimeForCooldownJob(jobs *breezemlv1.TrainingJobList) (bool, time.Duration) {
	rerun := false
	var rerunTime time.Duration

	now := time.Now()

	// find the nearest cooldown finish time
	for _, job := range jobs.Items {
		if job.Status.CooldownTime != nil {
			if !rerun {
				rerun = true
				rerunTime = job.Status.CooldownTime.Sub(now)
			} else {
				newRerunTime := job.Status.CooldownTime.Sub(now)
				if rerunTime > newRerunTime {
					rerunTime = newRerunTime
				}
			}
		}
	}

	return rerun, rerunTime
}

// Update the prometheus metrics
func UpdatePrometheusMetrics(trainingJobs *breezemlv1.TrainingJobList, totalNumResource int32, resourceName corev1.ResourceName) {
	// update job worker counts
	trainingoperatorcommon.LivePodsGaugeDeleteAllMetrics()
	for _, job := range trainingJobs.Items {
		trainingoperatorcommon.LivePodsGaugeSetValue(job.Namespace, string(job.UID), job.Status.CurrentSize)
	}

	// update cluster size
	trainingoperatorcommon.ClusterSizeGaugeSetValue(totalNumResource)

	// update active cluster size
	activeClusterSize := int32(0)
	for _, job := range trainingJobs.Items {
		jobResourceUsage := ResourceUsagePerPod(&job, resourceName)
		activeClusterSize += job.Status.CurrentSize * jobResourceUsage
	}
	trainingoperatorcommon.ActiveSizeGaugeSetValue(activeClusterSize)
}
