package autoscaler

import (
	"context"
	"fmt"
	"time"

	breezemlv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	commonv1 "github.com/kubeflow/common/pkg/apis/common/v1"
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/utils/pointer"
)

var _ = Describe("TrainingJob controller", func() {
	const (
		timeout      = time.Second * 10
		interval     = time.Millisecond * 250
		expectedPort = int32(8080)
	)

	Context("When creating the TrainingJob", func() {
		It("Should get the corresponding resources successfully", func() {
			const (
				namespace = "lattice"
				name      = "test-job"
			)
			By("By creating a new TrainingJob")
			ctx := context.Background()
			job := newTrainingJobForTest(name, namespace)
			job.Spec.RunPolicy = commonv1.RunPolicy{
				CleanPodPolicy: (*commonv1.CleanPodPolicy)(pointer.String(string(commonv1.CleanPodPolicyNone))),
			}
			job.Spec.MinSize = pointer.Int32(1)
			job.Spec.MaxSize = pointer.Int32(2)
			//job.Spec.InjectLattice = false
			job.Spec.ReplicaSpecs = &commonv1.ReplicaSpec{
				Replicas: pointer.Int32(1),
				Template: corev1.PodTemplateSpec{
					Spec: corev1.PodSpec{
						Containers: []corev1.Container{
							{
								Image: "test-image",
								Name:  breezemlv1.TrainingJobDefaultContainerName,
							},
						},
					},
				},
				RestartPolicy: commonv1.RestartPolicyAlways,
			}

			Expect(testK8sClient.Create(ctx, &corev1.Namespace{ObjectMeta: metav1.ObjectMeta{Name: namespace}})).Should(Succeed())
			Expect(testK8sClient.Create(ctx, job)).Should(Succeed())

			key := types.NamespacedName{Name: name, Namespace: namespace}
			created := &breezemlv1.TrainingJob{}

			// We'll need to retry getting this newly created TrainingJob, given that creation may not immediately happen.
			Eventually(func() bool {
				err := testK8sClient.Get(ctx, key, created)
				return err == nil
			}, timeout, interval).Should(BeTrue())

			workerKey := types.NamespacedName{Name: fmt.Sprintf("%s-worker-0", name), Namespace: namespace}
			workerPod := &corev1.Pod{}
			Eventually(func() bool {
				err := testK8sClient.Get(ctx, workerKey, workerPod)
				return err == nil
			}, timeout, interval).Should(BeTrue())

			workerSvc := &corev1.Service{}
			Eventually(func() bool {
				err := testK8sClient.Get(ctx, workerKey, workerSvc)
				return err == nil
			}, timeout, interval).Should(BeTrue())

			// Check service port.
			// Disabled since we didn't specify "ports" in the test job
			// Expect(workerSvc.Spec.Ports[0].Port).To(Equal(expectedPort))

			// Check owner reference.
			trueVal := true
			Expect(workerPod.OwnerReferences).To(ContainElement(metav1.OwnerReference{
				APIVersion:         breezemlv1.SchemeGroupVersion.String(),
				Kind:               breezemlv1.TrainingJobKind,
				Name:               name,
				UID:                created.UID,
				Controller:         &trueVal,
				BlockOwnerDeletion: &trueVal,
			}))
			Expect(workerSvc.OwnerReferences).To(ContainElement(metav1.OwnerReference{
				APIVersion:         breezemlv1.SchemeGroupVersion.String(),
				Kind:               breezemlv1.TrainingJobKind,
				Name:               name,
				UID:                created.UID,
				Controller:         &trueVal,
				BlockOwnerDeletion: &trueVal,
			}))

			// Test job status.
			workerPod.Status.Phase = corev1.PodSucceeded
			workerPod.ResourceVersion = ""
			Expect(testK8sClient.Status().Update(ctx, workerPod)).Should(Succeed())
			Eventually(func() bool {
				err := testK8sClient.Get(ctx, key, created)
				if err != nil {
					return false
				}
				return created.Status.ExecStatus.ReplicaStatuses != nil && created.Status.
					ExecStatus.ReplicaStatuses[breezemlv1.TrainingJobDefaultReplicaType].Succeeded == 1
			}, timeout, interval).Should(BeTrue())
			// Check if the job is succeeded.
			cond := getCondition(created.Status.ExecStatus, commonv1.JobSucceeded)
			Expect(cond.Status).To(Equal(corev1.ConditionTrue))
			By("Deleting the TrainingJob")
			Expect(testK8sClient.Delete(ctx, job)).Should(Succeed())
		})
	})
})

func newTrainingJobForTest(name, namespace string) *breezemlv1.TrainingJob {
	return &breezemlv1.TrainingJob{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: namespace,
		},
	}
}

// getCondition returns the condition with the provided type.
func getCondition(status commonv1.JobStatus, condType commonv1.JobConditionType) *commonv1.JobCondition {
	for _, condition := range status.Conditions {
		if condition.Type == condType {
			return &condition
		}
	}
	return nil
}
