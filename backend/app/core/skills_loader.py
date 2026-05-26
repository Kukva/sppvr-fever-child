"""
Загрузчик скиллов в формате Agent Skills (SKILL.md с YAML frontmatter).
Используется для загрузки системных промптов агентов из файловой системы.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Каталог скиллов относительно корня backend (или app)
DEFAULT_SKILLS_DIR = "skills"
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
YAML_NAME = re.compile(r"^name:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)
YAML_DESCRIPTION = re.compile(r"^description:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)


def _get_skills_base_path() -> Path:
    """Путь к каталогу skills: backend/skills или backend/app/skills."""
    # Из app/core/ идём в app, затем в parent (backend)
    app_core = Path(__file__).resolve().parent
    app_dir = app_core.parent
    backend_dir = app_dir.parent
    # Сначала пробуем backend/skills
    skills_in_backend = backend_dir / "skills"
    if skills_in_backend.is_dir():
        return skills_in_backend
    # Иначе backend/app/skills
    skills_in_app = app_dir / "skills"
    if skills_in_app.is_dir():
        return skills_in_app
    return skills_in_backend  # по умолчанию создаём в backend/skills


def load_skill(skill_id: str, base_path: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """
    Загружает один скилл по идентификатору (имя папки агента).
    
    Args:
        skill_id: Идентификатор скилла (например, intake, triage, synthesis).
        base_path: Корневой каталог скиллов. Если None, используется _get_skills_base_path().
    
    Returns:
        Словарь с ключами name, description, instructions или None, если скилл не найден/ошибка.
    """
    base = base_path or _get_skills_base_path()
    skill_dir = base / skill_id
    skill_file = skill_dir / "SKILL.md"
    
    if not skill_file.is_file():
        logger.debug(f"Skill file not found: {skill_file}")
        return None
    
    try:
        content = skill_file.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read skill {skill_id}: {e}")
        return None
    
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        logger.warning(f"Skill {skill_id}: no valid YAML frontmatter (--- ... ---)")
        return None
    
    yaml_block = match.group(1).strip()
    body = content[match.end() :].strip()
    
    name_match = YAML_NAME.search(yaml_block)
    desc_match = YAML_DESCRIPTION.search(yaml_block)
    name = name_match.group(1).strip() if name_match else skill_id
    description = desc_match.group(1).strip() if desc_match else ""
    
    if not body:
        logger.warning(f"Skill {skill_id}: empty instructions body")
    
    return {
        "name": name,
        "description": description,
        "instructions": body,
    }


def list_skills(base_path: Optional[Path] = None) -> List[Dict[str, str]]:
    """
    Discovery: возвращает список всех скиллов с полями name и description.
    
    Returns:
        Список словарей с ключами id, name, description.
    """
    base = base_path or _get_skills_base_path()
    result = []
    
    if not base.is_dir():
        return result
    
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        skill_id = entry.name
        if skill_id.startswith(".") or skill_id.startswith("_"):
            continue
        skill = load_skill(skill_id, base_path=base)
        if skill:
            result.append({
                "id": skill_id,
                "name": skill["name"],
                "description": skill["description"],
            })
    return result


def get_instructions_for_agent(agent_name: str, base_path: Optional[Path] = None) -> Optional[str]:
    """
    Возвращает только текст инструкций (instructions) для подстановки в системный промпт.
    Удобно для ai_studio: если не None — использовать как system prompt, иначе fallback.
    """
    skill = load_skill(agent_name, base_path=base_path)
    if skill and skill.get("instructions"):
        return skill["instructions"]
    return None
