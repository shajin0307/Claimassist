# Claims & Authorization Data-Quality Anomaly Monitor:

An AI-powered monitoring system for detecting anomalies and data-quality issues in healthcare authorization data. The system combines engineered authorization features, an Autoencoder for representation learning, and Logistic Regression for anomaly classification.

## 1. Project Overview 

Bad claims and authorization data can create downstream problems in payer analytics, care management, quality measurement, and operational workflows.

This project provides a machine-learning-based monitoring prototype that:

* Detects abnormal authorization records
* Calculates an anomaly probability/risk score
* Identifies suspicious authorization patterns
* Provides interpretable reasons for detected anomalies
* Supports real-time authorization analysis
* Supports batch/CSV analysis
* Provides a foundation for SLA and operational-risk monitoring    

The final ML model is deployed as an inference-only component. Training and experimentation are performed separately from the application.   

---

## 2. Final Machine Learning Model

The finalized model is:
   
**Autoencoder + Logistic Regression**

### Pipeline
                                                                              
```text
 Authorization Data
      ↓
Train / Validation / Test Split
      ↓
StandardScaler
      ↓
Dense Autoencoder
      ↓
8 Latent Features
      +
1 Reconstruction Error (MSE)
      ↓
   9 Features
      ↓
Logistic Regression
      ↓
Anomaly Probability
      ↓
Validation Threshold Selection
      ↓
Normal / Anomaly
      ↓
Untouched Test Data
      ↓
Final Evaluation
```

### Autoencoder

```text
Input       : 25
Hidden      : 16
Latent      : 8
Decoder     : 16
Output      : 25
```

Architecture:

```text
25 → 16 → 8 → 16 → 25
```

The Autoencoder produces:

* 8 dimension latent representation
* 1 reconstruction-error feature

These 9 features are passed to Logistic Regression.

### Logistic Regression

```text
class_weight = balanced
C            = 1.0
```

The final locked decision threshold is:

```text
0.81
```

The application must not tune this threshold using live, test, or production labels.

---

## 3. Final Model Performance

The finalized model was evaluated on an untouched held-out test set.

| Metric    | Result |
| --------- | -----: |
| Precision | 74.32% |
| Recall    | 77.67% |
| F1 Score  | 75.96% |
| Accuracy  | 94.10% |
| ROC-AUC   | 97.33% |
| PR-AUC    | 86.08% |

### Confusion Matrix

```text
TN = 4239
FP = 161
FN = 134
TP = 466
```

The model provides a better balance between precision and recall than the earlier 16-feature AE + Logistic Regression version.

---

## 4. Input Features

The final model uses 25 features.

### Original ML Features

```text
ml_req_units
ml_aprvd_units
ml_units_diff
ml_units_ratio
ml_latency_hours
ml_bene_carrier_cnt
ml_bene_outpatient_cnt
ml_bene_pde_cnt
ml_bene_total_utilization
ml_bene_gender
ml_bene_race
ml_bene_age
ml_prov_partd_clms
ml_prov_partd_cost
ml_prov_avg_cost_per_clm
has_partd_provider_match
```

### Engineered Features

```text
f_excessive_units
f_zero_approved
f_negative_latency
f_zero_latency
f_extreme_latency
f_provider_bene_activity
f_provider_cost_intensity
f_provider_mismatch
f_extreme_utilization
```

The feature engineering implementation used by the application must match the training pipeline exactly.

---

## 5. Supported Anomaly Patterns

The broader authorization dataset contains patterns such as:

```text
AFTER_DEATH_AUTH
DUPLICATE_AUTH_BURST
EXCESSIVE_UNITS_ANOMALY
GHOST_PROVIDER_AUTH
IMPOSSIBLE_DECISION_DATE
MASS_AUTO_APPROVAL
UNAUTHORIZED_SPECIALTY
```

The final 25-feature model focuses on the information represented by its approved input features and engineered signals.

Additional rule-based/domain features can be incorporated into the monitoring and explanation layers when appropriate.

---

## 6. Model Artifacts

The finalized model artifacts are stored in:

```text
backend/models/
```

Required files:

```text
autoencoder_final.pt
logistic_regression_final.pkl
scaler_final.pkl
imputer_final.pkl
feature_config_final.json
```

### Artifact Responsibilities

| File                            | Purpose                                         |
| ------------------------------- | ----------------------------------------------- |
| `autoencoder_final.pt`          | Trained PyTorch Autoencoder                     |
| `logistic_regression_final.pkl` | Final Logistic Regression classifier            |
| `scaler_final.pkl`              | Fitted feature scaler                           |
| `imputer_final.pkl`             | Fitted missing-value imputer                    |
| `feature_config_final.json`     | Feature definitions, architecture and threshold |

These artifacts are loaded for inference.

**The application does not retrain the model.**

---

## 7. Project Structure

```text
final_anomaly_system/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── model_service.py
│   │   ├── feature_engineering.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   ├── rules.py
│   │   └── explainability.py
│   │
│   ├── models/
│   │   ├── autoencoder_final.pt
│   │   ├── logistic_regression_final.pkl
│   │   ├── scaler_final.pkl
│   │   ├── imputer_final.pkl
│   │   └── feature_config_final.json
│   │
│   └── tests/
│       ├── test_model.py
│       └── test_api.py
│
├── frontend/
│
├── data/
│   └── sample/
│
├── docs/
│
├── requirements.txt
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 8. Inference Workflow

For a new authorization record:

```text
1. Receive authorization
        ↓
2. Validate input
        ↓
3. Generate 25 features
        ↓
4. Apply fitted imputer
        ↓
5. Apply fitted scaler
        ↓
6. Generate Autoencoder latent representation
        ↓
7. Calculate reconstruction error
        ↓
8. Combine 8 latent features + reconstruction error
        ↓
9. Logistic Regression prediction
        ↓
10. Apply threshold 0.81
        ↓
11. Generate risk level
        ↓
12. Generate explanation
        ↓
13. Store/display result
```

---

## 9. Prediction Output

A prediction should contain information similar to:

```json
{
  "auth_id": "AUTH_10001",
  "prediction": "ANOMALY",
  "probability": 0.94,
  "risk_level": "HIGH",
  "reasons": [
    "Excessive units",
    "Provider mismatch"
  ],
  "inference_latency_ms": 3.2
}
```

For a normal authorization:

```json
{
  "auth_id": "AUTH_10002",
  "prediction": "NORMAL",
  "probability": 0.08,
  "risk_level": "LOW",
  "reasons": [],
  "inference_latency_ms": 2.8
}
```

---

## 10. Explainability

The system should provide understandable reasons along with the model result.

Examples:

```text
Excessive units
Zero approved units
Negative decision latency
Extreme latency
Provider mismatch
Abnormal provider-beneficiary activity
High provider cost intensity
Extreme utilization
```

The explanation layer is separate from the trained classifier and does not modify the model prediction.

---

## 11. API

The backend is designed around FastAPI.

### Health Check

```text
GET /api/health
```

Expected information:

```text
Service status
Model loaded
Feature count
Model name
Decision threshold
```

### Single Authorization Prediction

```text
POST /api/predict
```

The endpoint accepts an authorization record and returns:

```text
Authorization ID
Prediction
Probability
Risk level
Explanation
Inference latency
```

### Batch Prediction

The application can support CSV/batch processing:

```text
CSV Upload
    ↓
Validation
    ↓
Feature Engineering
    ↓
Model Inference
    ↓
Prediction Results
```

---

## 12. Data Protection and Leakage Prevention

The following fields must never be used as model input during application inference:

```text
EXPECTED_ANOMALY
EXPECTED_TYPE
IS_ANOMALY
ANOMALY_TYPE
```

These fields represent labels or expected outcomes and would cause data leakage if included in inference.

The following project data files are treated as read-only:

```text
authorization_features_final.csv
feature_dictionary.csv
```

The application should not modify these files during prediction.

---

## 13. Database

The application can store prediction history for monitoring and dashboard purposes.

Recommended prediction-history fields:

```text
authorization_id
timestamp
prediction
probability
risk_level
explanation
inference_latency_ms
```

The database stores prediction results; it is not used to retrain the finalized model during normal application operation.

---

## 14. Dashboard

The frontend is intended to provide:

### Overview

```text
Total Authorizations
Normal Records
Anomalies
High-Risk Records
Average Risk
```

### Live Detection

Analyze an authorization and display:

```text
Prediction
Risk Score
Risk Level
Reasons
Processing Time
```

### History

Display previous predictions:

```text
Authorization ID
Timestamp
Risk Score
Prediction
Risk Level
```

### Analytics

Potential visualizations include:

* Normal vs anomaly distribution
* Risk-score distribution
* Anomaly trend
* High-risk authorization count
* Provider-related anomaly patterns

---

## 15. Testing

The backend should test:

```text
✓ Model artifact loading
✓ Feature count validation
✓ Threshold validation
✓ Autoencoder inference
✓ Logistic Regression inference
✓ Probability range
✓ Normal prediction
✓ Anomaly prediction
✓ API health endpoint
✓ Prediction endpoint
✓ Invalid input handling
✓ Batch/CSV inference
```

The model should always use the saved artifacts rather than retraining during application startup.

---

## 16. Important Model Integrity Rules

Do not:

```text
❌ Retrain the model inside the application
❌ Change the locked threshold
❌ Tune the threshold using test/live labels
❌ Use ground-truth fields during inference
❌ Modify the finalized model artifacts
❌ Change the feature definitions without retraining and re-evaluation
```

Do:

```text
✓ Load the saved model artifacts
✓ Use exactly 25 input features
✓ Apply the saved imputer
✓ Apply the saved scaler
✓ Use the Autoencoder representation
✓ Use Logistic Regression
✓ Use threshold 0.81
✓ Log inference latency
✓ Provide explanations separately from prediction
```

---

## 17. Limitations

The current model was evaluated using synthetic authorization data and a held-out test split.

Although the final model achieved strong held-out performance, additional validation on representative real-world payer authorization data is required before production deployment.

Fresh-data robustness experiments also showed that model performance can change when the feature distribution or anomaly-generation mechanism changes.

Therefore, the current system should be considered a **prototype/decision-support monitoring system**, not an autonomous production authorization decision-maker.

---

## 18. Future Enhancements

Possible future improvements include:

* Real payer authorization data validation
* More domain-specific temporal features
* Provider-beneficiary historical features
* Duplicate authorization sequence detection
* Specialty/procedure relationship rules
* Automated SLA-risk scoring
* Model monitoring and drift detection
* Probability calibration
* Human-review feedback loop
* Cloud deployment
* Role-based access control
* Audit logging
* Alert notifications

---

## 19. Running the Project

### Backend

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the API:

```bash
uvicorn backend.app.main:app --reload
```

Health check:

```text
GET /api/health
```

Prediction:

```text
POST /api/predict
```

### Frontend

The frontend can be started using the project's configured frontend development command.

### Docker

The project includes:

```text
docker-compose.yml
```

for containerized deployment of the application components.

---

## 20. Final Model Summary

```text
Model:
Autoencoder + Logistic Regression

Input Features:
25

Autoencoder:
25 → 16 → 8 → 16 → 25

Classifier:
Balanced Logistic Regression

Classifier Features:
8 latent features + reconstruction error

Locked Threshold:
0.81

Held-out Test F1:
75.96%

Held-out Test Precision:
74.32%

Held-out Test Recall:
77.67%

Held-out Test Accuracy:
94.10%

Held-out Test ROC-AUC:
97.33%

Held-out Test PR-AUC:
86.08%
```

---

## 21. Project Goal

The goal of the system is to provide an explainable and deployable monitoring layer for healthcare authorization data that can identify suspicious patterns early, quantify anomaly risk, and support payer operations teams in reviewing potentially problematic records.

**Final status: ML model finalized; application integration is the next stage.**
