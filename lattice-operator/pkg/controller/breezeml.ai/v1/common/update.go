// Derived from kubeflow/training-operator

package common

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ClearGeneratedFields will clear the generated fields from the given object meta.
// It is used to avoid problems like "the object has been modified; please apply your
// changes to the latest version and try again".
func ClearGeneratedFields(objmeta *metav1.ObjectMeta) {
	objmeta.UID = ""
	objmeta.CreationTimestamp = metav1.Time{}
}
