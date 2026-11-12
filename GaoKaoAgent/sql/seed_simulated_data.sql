-- All rows in this file are fictional examples for development only.
-- They are not official admission plans or historical admission results.
USE gaokao_agent;
START TRANSACTION;

INSERT INTO universities
  (name, province, city, level, source_name, source_url, applicable_year)
SELECT '模拟院校A', '上海', '上海', '模拟数据', '模拟数据', NULL, 2026
WHERE NOT EXISTS (SELECT 1 FROM universities WHERE name = '模拟院校A' AND province = '上海');

INSERT INTO majors
  (university_id, name, major_code, category, subject_requirements, source_name, source_url, applicable_year)
SELECT id, '模拟专业A', 'SIM-001', '模拟数据', '物理', '模拟数据', NULL, 2026
FROM universities WHERE name = '模拟院校A' AND province = '上海'
  AND NOT EXISTS (
    SELECT 1 FROM majors WHERE university_id = universities.id AND name = '模拟专业A'
  );

INSERT INTO admission_plans
  (university_id, major_id, province, exam_year, batch_name, planned_count,
   subject_requirements, source_name, source_url)
SELECT u.id, m.id, '上海', 2026, '模拟批次', 20, '物理', '模拟数据', NULL
FROM universities AS u JOIN majors AS m ON m.university_id = u.id
WHERE u.name = '模拟院校A' AND m.name = '模拟专业A'
  AND NOT EXISTS (
    SELECT 1 FROM admission_plans AS p
    WHERE p.university_id = u.id AND p.major_id = m.id
      AND p.province = '上海' AND p.exam_year = 2026 AND p.batch_name = '模拟批次'
  );

INSERT INTO admission_records
  (university_id, major_id, province, exam_year, batch_name, min_score,
   min_rank_no, source_name, source_url)
SELECT u.id, m.id, '上海', 2025, '模拟批次', 500.0, 10000, '模拟数据', NULL
FROM universities AS u JOIN majors AS m ON m.university_id = u.id
WHERE u.name = '模拟院校A' AND m.name = '模拟专业A'
  AND NOT EXISTS (
    SELECT 1 FROM admission_records AS r
    WHERE r.university_id = u.id AND r.major_id = m.id
      AND r.province = '上海' AND r.exam_year = 2025 AND r.batch_name = '模拟批次'
  );

-- Additional fictional candidates span reach, steady and safety rank bands.
INSERT INTO universities
  (name, province, city, level, source_name, source_url, applicable_year)
SELECT s.name, s.province, s.city, '模拟数据', '模拟数据', NULL, 2026
FROM (
  SELECT '模拟院校B' AS name, '上海' AS province, '上海' AS city UNION ALL
  SELECT '模拟院校C', '江苏', '苏州' UNION ALL
  SELECT '模拟院校D', '上海', '上海' UNION ALL
  SELECT '模拟院校E', '浙江', '杭州' UNION ALL
  SELECT '模拟院校F', '江苏', '南京' UNION ALL
  SELECT '模拟院校G', '上海', '上海' UNION ALL
  SELECT '模拟院校H', '上海', '上海' UNION ALL
  SELECT '模拟院校I', '上海', '上海'
) AS s
WHERE NOT EXISTS (SELECT 1 FROM universities AS u WHERE u.name = s.name AND u.province = s.province);

INSERT INTO majors
  (university_id, name, major_code, category, subject_requirements, source_name, source_url, applicable_year)
SELECT u.id, s.major_name, s.major_code, '模拟数据', s.subjects, '模拟数据', NULL, 2026
FROM (
  SELECT '模拟院校B' AS university_name, '模拟计算机科学与技术' AS major_name, 'SIM-002' AS major_code, '物理、化学' AS subjects UNION ALL
  SELECT '模拟院校C', '模拟软件工程', 'SIM-003', '物理' UNION ALL
  SELECT '模拟院校D', '模拟计算机应用', 'SIM-004', '物理' UNION ALL
  SELECT '模拟院校E', '模拟数据科学', 'SIM-005', '物理、化学' UNION ALL
  SELECT '模拟院校F', '模拟信息工程', 'SIM-006', '物理' UNION ALL
  SELECT '模拟院校G', '模拟历史学', 'SIM-007', '历史' UNION ALL
  SELECT '模拟院校H', '模拟历史教育', 'SIM-008', '历史' UNION ALL
  SELECT '模拟院校I', '模拟历史研究', 'SIM-009', '历史'
) AS s JOIN universities AS u ON u.name = s.university_name
WHERE NOT EXISTS (SELECT 1 FROM majors AS m WHERE m.university_id = u.id AND m.name = s.major_name);

INSERT INTO admission_plans
  (university_id, major_id, province, exam_year, batch_name, planned_count,
   subject_requirements, source_name, source_url)
SELECT u.id, m.id, '上海', 2026, '模拟批次', 20,
       m.subject_requirements, '模拟数据', NULL
FROM universities AS u JOIN majors AS m ON m.university_id = u.id
WHERE u.name IN ('模拟院校B', '模拟院校C', '模拟院校D', '模拟院校E', '模拟院校F', '模拟院校G', '模拟院校H', '模拟院校I')
  AND NOT EXISTS (
    SELECT 1 FROM admission_plans AS p WHERE p.university_id = u.id AND p.major_id = m.id
      AND p.province = '上海' AND p.exam_year = 2026 AND p.batch_name = '模拟批次'
  );

INSERT INTO admission_records
  (university_id, major_id, province, exam_year, batch_name, min_score,
   min_rank_no, source_name, source_url)
SELECT u.id, m.id, '上海', s.exam_year, '模拟批次', NULL,
       s.min_rank_no, '模拟数据', NULL
FROM (
  SELECT '模拟院校B' AS university_name, 6500 AS min_rank_no, 2025 AS exam_year UNION ALL
  SELECT '模拟院校C', 8500, 2025 UNION ALL
  SELECT '模拟院校D', 11500, 2025 UNION ALL
  SELECT '模拟院校E', 14500, 2025 UNION ALL
  SELECT '模拟院校F', 18000, 2025 UNION ALL
  SELECT '模拟院校G', 10000, 2025 UNION ALL
  SELECT '模拟院校H', 6500, 2023 UNION ALL
  SELECT '模拟院校I', 15000, 2023
) AS s JOIN universities AS u ON u.name = s.university_name
JOIN majors AS m ON m.university_id = u.id
WHERE NOT EXISTS (
  SELECT 1 FROM admission_records AS r WHERE r.university_id = u.id AND r.major_id = m.id
    AND r.province = '上海' AND r.exam_year = s.exam_year AND r.batch_name = '模拟批次'
);

COMMIT;

