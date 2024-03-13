package k8s

import (
	"fmt"
	"lattice-api-server/pkg/types"

	v1 "github.com/kubeflow/common/pkg/apis/common/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	"k8s.io/utils/pointer"
)

var (
	cleanPodPolicy = v1.CleanPodPolicy("None")
)

// some template TrainingJobSpecs
var (
	ExampleBertSpec = types.TrainingJobSpec{
		RunPolicy: v1.RunPolicy{
			CleanPodPolicy: &cleanPodPolicy,
		},
		MinSize:       pointer.Int32(1),
		MaxSize:       pointer.Int32(4),
		Priority:      pointer.Int32(0),
		InjectLattice: pointer.Bool(true),
		ReplicaSpecs: &v1.ReplicaSpec{
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:            "trainingjob",
							Image:           "breezeml/lattice-bert:1.0.1",
							ImagePullPolicy: "Always",
							Command: []string{
								"python",
							},
							Args: []string{
								"-u",
								"main.py",
							},
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									"nvidia.com/gpu": resource.MustParse("1"),
								},
								Limits: corev1.ResourceList{
									"nvidia.com/gpu": resource.MustParse("1"),
								},
							},
						},
					},
				},
			},
		},
	}

	ExampleResnetSpec = types.TrainingJobSpec{
		RunPolicy: v1.RunPolicy{
			CleanPodPolicy: &cleanPodPolicy,
		},
		MinSize:       pointer.Int32(1),
		MaxSize:       pointer.Int32(4),
		Priority:      pointer.Int32(0),
		InjectLattice: pointer.Bool(true),
		ReplicaSpecs: &v1.ReplicaSpec{
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					Containers: []corev1.Container{
						{
							Name:            "trainingjob",
							Image:           "breezeml/lattice-resnet:1.0.1",
							ImagePullPolicy: "Always",
							Command: []string{
								"python",
							},
							Args: []string{
								"-u",
								"main.py",
							},
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									"nvidia.com/gpu": resource.MustParse("1"),
								},
								Limits: corev1.ResourceList{
									"nvidia.com/gpu": resource.MustParse("1"),
								},
							},
						},
					},
				},
			},
		},
	}
)

// add the max epochs info into the job's arg
// need coordination from the docker image
// support our breezeml/resnet and breezeml/bert
func AddMaxEpochs(job *types.TrainingJob, epochs int64, prompt string) error {
	nContainer := len(job.Spec.ReplicaSpecs.Template.Spec.Containers)
	if nContainer != 1 {
		return fmt.Errorf("the trainingjob %s should have 1 container per pod (now %d)", job.Name, nContainer)
	}

	// append the argument
	argument := fmt.Sprintf("%s=%d", prompt, epochs)
	job.Spec.ReplicaSpecs.Template.Spec.Containers[0].Args = append(job.Spec.ReplicaSpecs.Template.Spec.Containers[0].Args, argument)
	return nil
}
