import json
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from app.feature_engineering import prepare_feature_dataframe, FINAL_FEATURES


class Autoencoder(nn.Module):
    def __init__(self, input_dim: int = 25, hidden_dim: int = 16, latent_dim: int = 8):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, latent_dim)
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, input_dim)
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent


class ModelService:
    def __init__(self, models_dir: Path = None):
        if models_dir is None:
            models_dir = Path(__file__).resolve().parent.parent / "models"
        self.models_dir = models_dir

        self.config: Dict[str, Any] = {}
        self.imputer = None
        self.scaler = None
        self.autoencoder: nn.Module = None
        self.logistic_regression = None
        self.is_loaded = False

        self.load_models()

    def load_models(self):
        """Load and validate all five model artifacts."""
        config_path = self.models_dir / "feature_config_final.json"
        imputer_path = self.models_dir / "imputer_final.pkl"
        scaler_path = self.models_dir / "scaler_final.pkl"
        autoencoder_path = self.models_dir / "autoencoder_final.pt"
        lr_path = self.models_dir / "logistic_regression_final.pkl"

        for p in [config_path, imputer_path, scaler_path, autoencoder_path, lr_path]:
            if not p.exists():
                raise FileNotFoundError(f"Model artifact missing: {p}")

        # 1. Load feature config
        with open(config_path, "r") as f:
            self.config = json.load(f)

        # Validate input_dim and threshold as requested
        input_dim = self.config.get("input_dim")
        if input_dim != 25:
            raise ValueError(f"Invalid input_dim in config: expected 25, got {input_dim}")

        threshold = self.config.get("threshold")
        if abs(threshold - 0.81) > 1e-4:
            raise ValueError(f"Invalid threshold in config: expected 0.81, got {threshold}")

        # 2. Load imputer
        self.imputer = joblib.load(imputer_path)
        if hasattr(self.imputer, "_fit_dtype") and not hasattr(self.imputer, "_fill_dtype"):
            self.imputer._fill_dtype = self.imputer._fit_dtype

        # 3. Load scaler
        self.scaler = joblib.load(scaler_path)
        if hasattr(self.scaler, "_fit_dtype") and not hasattr(self.scaler, "_fill_dtype"):
            self.scaler._fill_dtype = self.scaler._fit_dtype

        # 4. Load autoencoder (25 -> 16 -> 8 -> 16 -> 25)
        hidden_dim = self.config.get("hidden_dim", 16)
        latent_dim = self.config.get("latent_dim", 8)
        self.autoencoder = Autoencoder(input_dim=input_dim, hidden_dim=hidden_dim, latent_dim=latent_dim)
        state_dict = torch.load(autoencoder_path, map_location=torch.device("cpu"))
        self.autoencoder.load_state_dict(state_dict)
        self.autoencoder.eval()

        # 5. Load logistic regression
        self.logistic_regression = joblib.load(lr_path)

        self.is_loaded = True

    def predict(self, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Perform end-to-end inference and return probability, prediction, risk level, and reasons."""
        if not self.is_loaded:
            raise RuntimeError("Model service artifacts are not loaded.")

        start_time = time.perf_counter()

        auth_id = str(raw_input.get("auth_id", "AUTH_001"))

        # Feature engineering (25 features)
        df_features, rule_reasons = prepare_feature_dataframe(raw_input)

        # Impute and Scale
        imputed_array = self.imputer.transform(df_features)
        scaled_array = self.scaler.transform(imputed_array)

        # Convert to PyTorch Tensor
        x_tensor = torch.tensor(scaled_array, dtype=torch.float32)

        # Autoencoder forward pass
        with torch.no_grad():
            reconstructed, latent = self.autoencoder(x_tensor)
            # Calculate Reconstruction Error (MSE)
            recon_error = torch.mean((x_tensor - reconstructed) ** 2, dim=1, keepdim=True).numpy()
            latent_np = latent.numpy()

        # Meta-features: 8 latent features + 1 reconstruction error = 9 features
        meta_features = np.hstack([latent_np, recon_error])

        # Logistic Regression Prediction
        probabilities = self.logistic_regression.predict_proba(meta_features)[0]
        prob_anomaly = float(probabilities[1])

        threshold = self.config.get("threshold", 0.81)
        prediction = "ANOMALY" if prob_anomaly >= threshold else "NORMAL"

        # Risk level determination
        if prob_anomaly < 0.40:
            risk_level = "LOW"
        elif prob_anomaly < threshold:
            risk_level = "MEDIUM"
        elif prob_anomaly < 0.95:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"

        # Explanation reasons
        reasons = list(rule_reasons)
        if recon_error[0, 0] > 1.5:
            reasons.append("Elevated autoencoder reconstruction error indicating atypical pattern.")
        if prediction == "ANOMALY" and not reasons:
            reasons.append("High overall anomaly probability score from combined ML model.")

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 3)

        return {
            "auth_id": auth_id,
            "prediction": prediction,
            "probability": round(prob_anomaly, 4),
            "risk_level": risk_level,
            "reasons": reasons,
            "inference_latency_ms": latency_ms,
        }
