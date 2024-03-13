// Copyright 2022 The BreezeML Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Code generated by client-gen. DO NOT EDIT.

package fake

import (
	"context"

	breezemlaiv1 "github.com/breezeml/lattice-operator/pkg/apis/breezeml.ai/v1"
	v1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	labels "k8s.io/apimachinery/pkg/labels"
	schema "k8s.io/apimachinery/pkg/runtime/schema"
	types "k8s.io/apimachinery/pkg/types"
	watch "k8s.io/apimachinery/pkg/watch"
	testing "k8s.io/client-go/testing"
)

// FakeTrainingJobs implements TrainingJobInterface
type FakeTrainingJobs struct {
	Fake *FakeBreezemlV1
	ns   string
}

var trainingjobsResource = schema.GroupVersionResource{Group: "breezeml.ai", Version: "v1", Resource: "trainingjobs"}

var trainingjobsKind = schema.GroupVersionKind{Group: "breezeml.ai", Version: "v1", Kind: "TrainingJob"}

// Get takes name of the trainingJob, and returns the corresponding trainingJob object, and an error if there is any.
func (c *FakeTrainingJobs) Get(ctx context.Context, name string, options v1.GetOptions) (result *breezemlaiv1.TrainingJob, err error) {
	obj, err := c.Fake.
		Invokes(testing.NewGetAction(trainingjobsResource, c.ns, name), &breezemlaiv1.TrainingJob{})

	if obj == nil {
		return nil, err
	}
	return obj.(*breezemlaiv1.TrainingJob), err
}

// List takes label and field selectors, and returns the list of TrainingJobs that match those selectors.
func (c *FakeTrainingJobs) List(ctx context.Context, opts v1.ListOptions) (result *breezemlaiv1.TrainingJobList, err error) {
	obj, err := c.Fake.
		Invokes(testing.NewListAction(trainingjobsResource, trainingjobsKind, c.ns, opts), &breezemlaiv1.TrainingJobList{})

	if obj == nil {
		return nil, err
	}

	label, _, _ := testing.ExtractFromListOptions(opts)
	if label == nil {
		label = labels.Everything()
	}
	list := &breezemlaiv1.TrainingJobList{ListMeta: obj.(*breezemlaiv1.TrainingJobList).ListMeta}
	for _, item := range obj.(*breezemlaiv1.TrainingJobList).Items {
		if label.Matches(labels.Set(item.Labels)) {
			list.Items = append(list.Items, item)
		}
	}
	return list, err
}

// Watch returns a watch.Interface that watches the requested trainingJobs.
func (c *FakeTrainingJobs) Watch(ctx context.Context, opts v1.ListOptions) (watch.Interface, error) {
	return c.Fake.
		InvokesWatch(testing.NewWatchAction(trainingjobsResource, c.ns, opts))

}

// Create takes the representation of a trainingJob and creates it.  Returns the server's representation of the trainingJob, and an error, if there is any.
func (c *FakeTrainingJobs) Create(ctx context.Context, trainingJob *breezemlaiv1.TrainingJob, opts v1.CreateOptions) (result *breezemlaiv1.TrainingJob, err error) {
	obj, err := c.Fake.
		Invokes(testing.NewCreateAction(trainingjobsResource, c.ns, trainingJob), &breezemlaiv1.TrainingJob{})

	if obj == nil {
		return nil, err
	}
	return obj.(*breezemlaiv1.TrainingJob), err
}

// Update takes the representation of a trainingJob and updates it. Returns the server's representation of the trainingJob, and an error, if there is any.
func (c *FakeTrainingJobs) Update(ctx context.Context, trainingJob *breezemlaiv1.TrainingJob, opts v1.UpdateOptions) (result *breezemlaiv1.TrainingJob, err error) {
	obj, err := c.Fake.
		Invokes(testing.NewUpdateAction(trainingjobsResource, c.ns, trainingJob), &breezemlaiv1.TrainingJob{})

	if obj == nil {
		return nil, err
	}
	return obj.(*breezemlaiv1.TrainingJob), err
}

// UpdateStatus was generated because the type contains a Status member.
// Add a +genclient:noStatus comment above the type to avoid generating UpdateStatus().
func (c *FakeTrainingJobs) UpdateStatus(ctx context.Context, trainingJob *breezemlaiv1.TrainingJob, opts v1.UpdateOptions) (*breezemlaiv1.TrainingJob, error) {
	obj, err := c.Fake.
		Invokes(testing.NewUpdateSubresourceAction(trainingjobsResource, "status", c.ns, trainingJob), &breezemlaiv1.TrainingJob{})

	if obj == nil {
		return nil, err
	}
	return obj.(*breezemlaiv1.TrainingJob), err
}

// Delete takes name of the trainingJob and deletes it. Returns an error if one occurs.
func (c *FakeTrainingJobs) Delete(ctx context.Context, name string, opts v1.DeleteOptions) error {
	_, err := c.Fake.
		Invokes(testing.NewDeleteActionWithOptions(trainingjobsResource, c.ns, name, opts), &breezemlaiv1.TrainingJob{})

	return err
}

// DeleteCollection deletes a collection of objects.
func (c *FakeTrainingJobs) DeleteCollection(ctx context.Context, opts v1.DeleteOptions, listOpts v1.ListOptions) error {
	action := testing.NewDeleteCollectionAction(trainingjobsResource, c.ns, listOpts)

	_, err := c.Fake.Invokes(action, &breezemlaiv1.TrainingJobList{})
	return err
}

// Patch applies the patch and returns the patched trainingJob.
func (c *FakeTrainingJobs) Patch(ctx context.Context, name string, pt types.PatchType, data []byte, opts v1.PatchOptions, subresources ...string) (result *breezemlaiv1.TrainingJob, err error) {
	obj, err := c.Fake.
		Invokes(testing.NewPatchSubresourceAction(trainingjobsResource, c.ns, name, pt, data, subresources...), &breezemlaiv1.TrainingJob{})

	if obj == nil {
		return nil, err
	}
	return obj.(*breezemlaiv1.TrainingJob), err
}
