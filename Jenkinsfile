pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
metadata:
  labels:
    app: jenkins
    horizon-build: 'true'
spec:
  containers:
    - name: python
      image: ghcr.io/astral-sh/uv:python3.11-bookworm-slim
      command: [sleep]
      args: [99d]
      resources:
        requests: {cpu: 100m, memory: 256Mi}
        limits: {cpu: '2', memory: 2Gi}
    - name: kaniko
      image: gcr.io/kaniko-project/executor:v1.23.2-debug
      command: [/busybox/sleep]
      args: ['9999999']
      resources:
        requests: {cpu: 100m, memory: 512Mi, ephemeral-storage: 2Gi}
        limits: {cpu: '2', memory: 4Gi, ephemeral-storage: 16Gi}
    - name: kubectl
      image: alpine/k8s:1.30.14
      command: [sleep]
      args: [99d]
      resources:
        requests: {cpu: 50m, memory: 64Mi}
        limits: {cpu: '0.5', memory: 256Mi}
    - name: jnlp
      resources:
        requests: {cpu: 100m, memory: 128Mi}
        limits: {cpu: '1', memory: 512Mi}
'''
        }
    }
    options {
        timeout(time: 45, unit: 'MINUTES')
        disableConcurrentBuilds()
        skipDefaultCheckout()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    triggers { pollSCM('H/5 * * * *') }
    environment {
        REGISTRY = '192.168.1.10:30004'
        IMAGE_REPOSITORY = '192.168.1.10:30004/horizon'
    }
    stages {
        stage('Checkout main') {
            steps {
                script {
                    def source = git branch: 'main', credentialsId: 'cloudbeaver-git', url: 'https://github.com/hotienvu01/Horizon.git'
                    env.SOURCE_REVISION = source.GIT_COMMIT
                    env.IMAGE_TAG = "${source.GIT_COMMIT.take(12)}-${env.BUILD_NUMBER}"
                    currentBuild.description = "main ${source.GIT_COMMIT.take(12)}"
                }
            }
        }
        stage('Test') {
            steps {
                container('python') {
                    sh 'uv sync --frozen --extra dev && uv run --no-sync pytest --junitxml=test-results.xml'
                }
            }
            post { always { junit 'test-results.xml' } }
        }
        stage('Build and push immutable image') {
            steps {
                container('kaniko') {
                    withCredentials([usernamePassword(credentialsId: 'nexus-cred', usernameVariable: 'NEXUS_USER', passwordVariable: 'NEXUS_PASSWORD')]) {
                        sh '''
set +x
set -eu
mkdir -p /kaniko/.docker
AUTH=$(printf '%s:%s' "$NEXUS_USER" "$NEXUS_PASSWORD" | base64 | tr -d '\n')
printf '{"auths":{"%s":{"auth":"%s"}}}' "$REGISTRY" "$AUTH" > /kaniko/.docker/config.json
chmod 600 /kaniko/.docker/config.json
trap 'rm -f /kaniko/.docker/config.json' EXIT
/kaniko/executor --use-new-run --snapshot-mode=redo --context="$WORKSPACE" --dockerfile="$WORKSPACE/Dockerfile" \
  --destination="$IMAGE_REPOSITORY:$IMAGE_TAG" --digest-file="$WORKSPACE/image-digest.txt" \
  --label="org.opencontainers.image.revision=$SOURCE_REVISION" \
  --insecure --insecure-registry="$REGISTRY" \
  --cache=true --compressed-caching=false --cache-repo="$REGISTRY/horizon-cache" --cache-ttl=168h
'''
                    }
                }
                script {
                    def digest = readFile('image-digest.txt').trim()
                    if (!(digest ==~ /sha256:[a-f0-9]{64}/)) { error('Invalid built-image digest') }
                    env.IMAGE_REFERENCE = "${env.IMAGE_REPOSITORY}@${digest}"
                    echo "Verified image: ${env.IMAGE_REFERENCE}"
                }
                archiveArtifacts artifacts: 'image-digest.txt', fingerprint: true
            }
        }
        stage('Deploy and verify Kubernetes') {
            steps {
                container('kubectl') {
                    withCredentials([file(credentialsId: 'kube-config', variable: 'KUBECONFIG'), usernamePassword(credentialsId: 'nexus-cred', usernameVariable: 'NEXUS_USER', passwordVariable: 'NEXUS_PASSWORD')]) {
                        sh '''
set +x
set -eu
kubectl create namespace horizon --dry-run=client -o yaml | kubectl apply -f -
umask 077
AUTH=$(printf '%s:%s' "$NEXUS_USER" "$NEXUS_PASSWORD" | base64 | tr -d '\n')
printf '{"auths":{"%s":{"auth":"%s"}}}' "$REGISTRY" "$AUTH" > /tmp/horizon-registry.json
trap 'rm -f /tmp/horizon-registry.json' EXIT
kubectl -n horizon create secret generic nexus-regcred --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson=/tmp/horizon-registry.json --dry-run=client -o yaml | kubectl apply --server-side --field-manager=horizon-jenkins -f -
kubectl -n horizon create configmap horizon-config --from-file=config.json=deploy/config.json --dry-run=client -o yaml | kubectl apply -f -
sed "s|HORIZON_IMAGE|$IMAGE_REFERENCE|g" deploy/kubernetes.yaml > /tmp/horizon.yaml
kubectl apply --dry-run=server -f /tmp/horizon.yaml
kubectl apply -f /tmp/horizon.yaml
# Exercise the built runtime and PVC without invoking a paid AI provider.
kubectl -n horizon create job --from=cronjob/horizon horizon-smoke-$BUILD_NUMBER --dry-run=client -o json | jq '.spec.template.spec.containers[0].command=["/app/.venv/bin/horizon"] | .spec.template.spec.containers[0].args=["--help"]' | kubectl apply -f -
kubectl -n horizon wait --for=condition=complete job/horizon-smoke-$BUILD_NUMBER --timeout=300s
kubectl -n horizon logs job/horizon-smoke-$BUILD_NUMBER
kubectl -n horizon get cronjob,pvc
'''
                    }
                }
            }
        }
    }
    post { always { cleanWs() } }
}
