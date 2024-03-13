package util

import (
	"fmt"
	"strconv"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	commonutil "github.com/kubeflow/common/pkg/util"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/pointer"
)

var _ = Describe("TrainingJob controller", func() {
	const (
		namespace   = "trainingjob"
		namePrefix  = "test-job"
		minSize     = 2
		maxSize     = 4
		clusterSize = 5
	)

	Context("When a new job is added to the cluster", func() {
		It("the operator should recognize it", func() {
			var jobs breezemlv1.TrainingJobList
			jobs.Items = append(jobs.Items, *newTrainingJobForTest(getTrainingJobName(namePrefix, int32(1)), namespace, minSize, maxSize))
			job1 := &(jobs.Items[0])

			By("by changing its stage to waiting and setting up the submission timestamp")

			Expect(ResetJobStatus(&jobs)).To(Succeed())
			Expect(job1.Status.SubmitTime).ToNot(BeNil())
			Expect(job1.Status.Stage).To(Equal(breezemlv1.TrainingJobStageWaiting))

			var priorityList []*breezemlv1.TrainingJob
			var runningList []*breezemlv1.TrainingJob
			var waitingList []*breezemlv1.TrainingJob

			By("we can successfully sort all jobs based on their priority")
			Expect(ConstructPriorityList(&jobs, &priorityList, clusterSize)).To(Succeed())

			resourceName := v1.ResourceName(NodeResourceType)

			By("we then dispatch workers to jobs")
			Expect(DispatchWorkers(&priorityList, clusterSize, resourceName)).To(Succeed())

			By("we can successfully construct the running and waiting list")
			Expect(ConstructSchedulingLists(&priorityList, &runningList, &waitingList, clusterSize)).To(Succeed())

			By("and try to squeeze new jobs in")
			Expect(StartWaitingJobs(&runningList, &waitingList, clusterSize, resourceName, nil)).To(Succeed())

			By("it should then be put into the running list")
			Expect(len(runningList)).To(Equal(1))
			Expect(len(waitingList)).To(Equal(0))

			By("the job should run with maximum size")
			Expect(job1.Status.CurrentSize).To(Equal(int32(maxSize)))

			By("now we have a new job and repeat all the process")
			jobs.Items = append(jobs.Items, *newTrainingJobForTest(getTrainingJobName(namePrefix, int32(2)), namespace, minSize, maxSize))
			job1 = &(jobs.Items[0])
			job2 := &(jobs.Items[1])
			Expect(ResetJobStatus(&jobs)).To(Succeed())

			priorityList = nil
			runningList = nil
			waitingList = nil

			Expect(ConstructPriorityList(&jobs, &priorityList, clusterSize)).To(Succeed())
			Expect(DispatchWorkers(&priorityList, clusterSize, resourceName)).To(Succeed())
			Expect(ConstructSchedulingLists(&priorityList, &runningList, &waitingList, clusterSize)).To(Succeed())

			Expect(len(runningList)).To(Equal(1))
			Expect(len(waitingList)).To(Equal(1))

			Expect(StartWaitingJobs(&runningList, &waitingList, clusterSize, resourceName, nil)).To(Succeed())

			By("the new job should be running with 2 workers")
			Expect(len(runningList)).To(Equal(2))
			Expect(len(waitingList)).To(Equal(0))

			Expect(job1.Status.CurrentSize).To(Equal(int32(3)))
			Expect(job2.Status.CurrentSize).To(Equal(int32(2)))
		})
	})
})

func newTrainingJobForTest(name, namespace string, minSize int32, maxSize int32) *breezemlv1.TrainingJob {
	job := breezemlv1.TrainingJob{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
	}
	breezemlv1.SetDefaults_TrainingJob(&job)
	job.Spec.MinSize = pointer.Int32(minSize)
	job.Spec.MaxSize = pointer.Int32(maxSize)

	running_pod := int32(0) // current running pods for the job
	for _, v := range job.Status.ExecStatus.ReplicaStatuses {
		running_pod += v.Active
	}

	msg := fmt.Sprintf("TrainingJob %s is created.", job.Name)
	if err := commonutil.UpdateJobConditions(&job.Status.ExecStatus, commonv1.JobCreated, "TrainingJobCreated", msg); err != nil {
		return nil
	}

	return &job
}

func getTrainingJobName(prefix string, number int32) string {
	return prefix + "-" + strconv.FormatInt(int64(number), 10)
}
