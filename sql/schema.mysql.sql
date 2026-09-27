-- MySQL / MariaDB schema for drscreen (generated from src/drscreen/storage.py).
-- `drscreen init-db` creates these automatically; this file is for DBAs / HeidiSQL.

CREATE DATABASE IF NOT EXISTS drscreen CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE drscreen;

CREATE TABLE operators (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
) ENGINE=InnoDB;

CREATE TABLE patients (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	full_name VARCHAR(120) NOT NULL, 
	phone VARCHAR(20), 
	age SMALLINT, 
	sex VARCHAR(1), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_patient_identity UNIQUE (full_name, phone)
) ENGINE=InnoDB;

CREATE TABLE screenings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	patient_id INTEGER NOT NULL, 
	operator_id INTEGER, 
	image_path VARCHAR(512) NOT NULL, 
	image_sha256 VARCHAR(64), 
	grade SMALLINT NOT NULL, 
	confidence FLOAT NOT NULL, 
	referral_probability FLOAT NOT NULL, 
	referable BOOL NOT NULL, 
	probabilities JSON NOT NULL, 
	model_version VARCHAR(64) NOT NULL, 
	sms_status VARCHAR(16), 
	sms_sid VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id), 
	FOREIGN KEY(operator_id) REFERENCES operators (id)
) ENGINE=InnoDB;
CREATE INDEX ix_screenings_created_at ON screenings (created_at);
CREATE INDEX ix_screenings_image_sha256 ON screenings (image_sha256);
CREATE INDEX ix_screenings_patient_id ON screenings (patient_id);

-- Least-privilege application account (replace the password):
-- CREATE USER 'drscreen'@'localhost' IDENTIFIED BY 'change-me';
-- GRANT SELECT, INSERT, UPDATE ON drscreen.* TO 'drscreen'@'localhost';
