// Copyright 2023 The BreezeML Authors
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
// limitations under the License

package config

// Config is the global configuration for the training operator.
var Config struct {
	TrainingInitContainerTemplateFile string
	TrainingInitContainerImage        string
}

const (
	// TrainingInitContainerImageDefault is the default image for the training
	// init container.
	TrainingInitContainerImageDefault = "alpine:3.10"
	// TrainingInitContainerTemplateFileDefault is the default template file for
	// the training init container.
	TrainingInitContainerTemplateFileDefault = "/etc/config/initContainer.yaml"
)
