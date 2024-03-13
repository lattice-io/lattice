kubeconfig:
	$(eval region=$(shell terraform output -raw region))
	$(eval cluster_name=$(shell terraform output -raw cluster_name))
	aws eks update-kubeconfig --region ${region} --name ${cluster_name}
