eks-kubeconfig:
	aws eks update-kubeconfig --name lattice_dashboard_ingress_4_node --region ap-southeast-1

nginx-ingress:
	NIGNX_DIR := ./sys_monitor_deploy/nginx_ingress_controller
	kubectl apply -f ${NIGNX_DIR}/deploy.yaml


kubectl apply --server-side -f manifests/setup
kubectl wait \
	--for condition=Established \
	--all CustomResourceDefinition \
	--namespace=monitoring
kubectl apply -f manifests/
