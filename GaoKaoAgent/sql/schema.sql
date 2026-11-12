CREATE DATABASE IF NOT EXISTS gaokao_agent
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE gaokao_agent;

CREATE TABLE IF NOT EXISTS students (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  province VARCHAR(50) NOT NULL,
  exam_year SMALLINT UNSIGNED NOT NULL,
  score DECIMAL(6,1) NOT NULL,
  rank_no INT UNSIGNED NOT NULL,
  subject_combination VARCHAR(100) NOT NULL,
  interests JSON NULL,
  target_cities JSON NULL,
  risk_preference ENUM('conservative','balanced','aggressive') NOT NULL DEFAULT 'balanced',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_students_province_year (province, exam_year),
  CONSTRAINT chk_students_score CHECK (score >= 0),
  CONSTRAINT chk_students_rank CHECK (rank_no > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS student_profiles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id BIGINT UNSIGNED NOT NULL,
  profile_json JSON NOT NULL,
  validation_warnings JSON NULL,
  generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_profiles_student (student_id, generated_at),
  CONSTRAINT fk_profiles_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS universities (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(200) NOT NULL,
  province VARCHAR(50) NOT NULL,
  city VARCHAR(50) NOT NULL,
  level VARCHAR(100) NULL,
  source_name VARCHAR(200) NOT NULL,
  source_url VARCHAR(1000) NULL,
  applicable_year SMALLINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_university_name_province (name, province),
  KEY idx_universities_city (city)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS majors (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  university_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(200) NOT NULL,
  major_code VARCHAR(50) NULL,
  category VARCHAR(100) NULL,
  subject_requirements VARCHAR(200) NULL,
  source_name VARCHAR(200) NOT NULL,
  source_url VARCHAR(1000) NULL,
  applicable_year SMALLINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_majors_id_university (id, university_id),
  UNIQUE KEY uq_major_university_name (university_id, name),
  KEY idx_majors_name (name),
  CONSTRAINT fk_majors_university FOREIGN KEY (university_id) REFERENCES universities(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admission_plans (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  university_id BIGINT UNSIGNED NOT NULL,
  major_id BIGINT UNSIGNED NOT NULL,
  province VARCHAR(50) NOT NULL,
  exam_year SMALLINT UNSIGNED NOT NULL,
  batch_name VARCHAR(100) NOT NULL,
  planned_count INT UNSIGNED NOT NULL,
  subject_requirements VARCHAR(200) NULL,
  source_name VARCHAR(200) NOT NULL,
  source_url VARCHAR(1000) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admission_plan (province, exam_year, university_id, major_id, batch_name),
  KEY idx_plans_major (major_id),
  CONSTRAINT fk_plans_university FOREIGN KEY (university_id) REFERENCES universities(id) ON DELETE RESTRICT,
  CONSTRAINT fk_plans_major_university FOREIGN KEY (major_id, university_id)
    REFERENCES majors(id, university_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admission_records (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  university_id BIGINT UNSIGNED NOT NULL,
  major_id BIGINT UNSIGNED NOT NULL,
  province VARCHAR(50) NOT NULL,
  exam_year SMALLINT UNSIGNED NOT NULL,
  batch_name VARCHAR(100) NOT NULL,
  min_score DECIMAL(6,1) NULL,
  min_rank_no INT UNSIGNED NULL,
  source_name VARCHAR(200) NOT NULL,
  source_url VARCHAR(1000) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admission_record (province, exam_year, university_id, major_id, batch_name),
  KEY idx_records_major (major_id),
  CONSTRAINT fk_records_university FOREIGN KEY (university_id) REFERENCES universities(id) ON DELETE RESTRICT,
  CONSTRAINT fk_records_major_university FOREIGN KEY (major_id, university_id)
    REFERENCES majors(id, university_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workflow_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(30) NOT NULL,
  current_node VARCHAR(100) NULL,
  adjustment_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  max_adjustments SMALLINT UNSIGNED NOT NULL DEFAULT 2,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_runs_student (student_id, started_at),
  CONSTRAINT fk_runs_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recommendation_plans (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  student_id BIGINT UNSIGNED NOT NULL,
  exam_year SMALLINT UNSIGNED NOT NULL,
  status VARCHAR(30) NOT NULL,
  workflow_run_id BIGINT UNSIGNED NULL,
  summary TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_recommendations_student (student_id, created_at),
  UNIQUE KEY uq_recommendations_run (workflow_run_id),
  CONSTRAINT fk_recommendations_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE RESTRICT,
  CONSTRAINT fk_recommendations_run FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS recommendation_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  plan_id BIGINT UNSIGNED NOT NULL,
  university_id BIGINT UNSIGNED NOT NULL,
  major_id BIGINT UNSIGNED NOT NULL,
  tier ENUM('冲','稳','保') NOT NULL,
  match_score DECIMAL(5,2) NOT NULL,
  reason_text TEXT NOT NULL,
  evidence_json JSON NULL,
  risk_level VARCHAR(30) NULL,
  risk_notes TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_items_plan_tier (plan_id, tier),
  KEY idx_items_university (university_id),
  KEY idx_items_major (major_id),
  CONSTRAINT fk_items_plan FOREIGN KEY (plan_id) REFERENCES recommendation_plans(id) ON DELETE RESTRICT,
  CONSTRAINT fk_items_university FOREIGN KEY (university_id) REFERENCES universities(id) ON DELETE RESTRICT,
  CONSTRAINT fk_items_major_university FOREIGN KEY (major_id, university_id)
    REFERENCES majors(id, university_id) ON DELETE RESTRICT,
  CONSTRAINT chk_items_score CHECK (match_score >= 0 AND match_score <= 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workflow_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  workflow_run_id BIGINT UNSIGNED NOT NULL,
  agent_name VARCHAR(100) NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  status VARCHAR(30) NOT NULL,
  input_summary TEXT NULL,
  output_summary TEXT NULL,
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_events_run_created (workflow_run_id, created_at),
  CONSTRAINT fk_events_run FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  original_name VARCHAR(255) NOT NULL,
  file_type VARCHAR(20) NOT NULL,
  storage_path VARCHAR(1000) NOT NULL,
  document_type VARCHAR(100) NOT NULL,
  source_name VARCHAR(200) NOT NULL,
  source_url VARCHAR(1000) NULL,
  applicable_region VARCHAR(100) NULL,
  applicable_year SMALLINT UNSIGNED NULL,
  published_at DATETIME NULL,
  ingest_status VARCHAR(30) NOT NULL DEFAULT 'pending',
  uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_documents_status (ingest_status, applicable_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id BIGINT UNSIGNED NOT NULL,
  chunk_index INT UNSIGNED NOT NULL,
  content TEXT NOT NULL,
  page_or_section VARCHAR(100) NULL,
  chroma_id VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_chunks_document_index (document_id, chunk_index),
  UNIQUE KEY uq_chunks_chroma_id (chroma_id),
  CONSTRAINT fk_chunks_document FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS operation_logs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  operation_type VARCHAR(100) NOT NULL,
  target_type VARCHAR(100) NOT NULL,
  target_id BIGINT UNSIGNED NULL,
  detail_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_logs_target (target_type, target_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

