{{/*
Expand the name of the chart.
*/}}
{{- define "ml-portal.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ml-portal.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "ml-portal.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ml-portal.labels" -}}
helm.sh/chart: {{ include "ml-portal.chart" . }}
{{ include "ml-portal.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
environment: {{ .Values.global.environment }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ml-portal.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ml-portal.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "ml-portal.frontend.labels" -}}
{{ include "ml-portal.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
API labels
*/}}
{{- define "ml-portal.api.labels" -}}
{{ include "ml-portal.labels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
Workers labels
*/}}
{{- define "ml-portal.workers.labels" -}}
{{ include "ml-portal.labels" . }}
app.kubernetes.io/component: workers
{{- end }}

{{/*
Embedding labels
*/}}
{{- define "ml-portal.embedding.labels" -}}
{{ include "ml-portal.labels" . }}
app.kubernetes.io/component: embedding
{{- end }}

{{/*
Image pull secrets
*/}}
{{- define "ml-portal.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.global.imagePullSecrets }}
  - name: {{ .name }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Full image name
*/}}
{{- define "ml-portal.image" -}}
{{- $registry := .registry -}}
{{- $repository := .repository -}}
{{- $tag := .tag | default "latest" -}}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- end }}
