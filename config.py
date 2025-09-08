import os
from pathlib import Path
from typing import List, Dict, Any
from collections import OrderedDict
from pydantic import BaseModel, Field
from utils.schema import VibeStepMetadata
import yaml
from dotenv import load_dotenv

from logger import logger

load_dotenv()

CONFIG_FILENAME = "config.yaml"
PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / CONFIG_FILENAME


class OrderedDumper(yaml.SafeDumper):
    """Custom YAML dumper that preserves order for OrderedDict and regular dicts"""
    pass


def dict_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        data.items()
    )


def ordered_dict_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        data.items()
    )


# Register the representers
OrderedDumper.add_representer(OrderedDict, ordered_dict_representer)
OrderedDumper.add_representer(dict, dict_representer)


class Workflow(BaseModel):
    name: str = Field(description="The short name of the workflow.")
    description: str = Field(description="The description of the workflow.", default="")
    overall_goal: str = Field(description="The overall goal of the workflow.")
    steps: List[VibeStepMetadata] = Field(description="The steps of the workflow.")
    
    def to_ordered_dict(self) -> OrderedDict:
        """Convert to OrderedDict maintaining field order"""
        ordered_dict = OrderedDict()
        ordered_dict["name"] = self.name
        ordered_dict["description"] = self.description
        ordered_dict["overall_goal"] = self.overall_goal
        ordered_dict["steps"] = [step.to_ordered_dict() for step in self.steps]
        return ordered_dict

class Config(BaseModel):
    llm_base_url: str = Field(default=os.getenv("LLM_BASE_URL", ""))
    llm_api_key: str = Field(default=os.getenv("LLM_API_KEY", "EMPTY"))
    llm_model: str = Field(default=os.getenv("LLM_MODEL", ""))
    mcp_urls: List[str] = Field(default_factory=list)
    workflows: List[Workflow] = Field(default_factory=list)
    
    def to_ordered_dict(self) -> OrderedDict:
        """Convert to OrderedDict maintaining field order"""
        ordered_dict = OrderedDict()
        ordered_dict["llm_api_key"] = self.llm_api_key
        ordered_dict["llm_base_url"] = self.llm_base_url
        ordered_dict["llm_model"] = self.llm_model
        ordered_dict["mcp_urls"] = self.mcp_urls
        ordered_dict["workflows"] = [workflow.to_ordered_dict() for workflow in self.workflows]
        return ordered_dict

    @classmethod
    def load(cls) -> "Config":
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                config = cls(**data)
            else:
                # Create default config if file doesn't exist
                config = cls()
                config.save()
                
            return config
        except Exception as e:
            logger.error(f"Error loading config from {CONFIG_PATH}: {e}")
            logger.error("Using default configuration...")
            return cls()

    def save(self) -> bool:
        try:
            # Ensure directory exists
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to ordered dict to maintain field order
            data = self.to_ordered_dict()
            
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(data, f, Dumper=OrderedDumper, default_flow_style=False, allow_unicode=True, indent=2)
            
            print(f"Configuration saved to {CONFIG_PATH}")
            return True
        except Exception as e:
            logger.error(f"Error saving config to {CONFIG_PATH}: {e}")
            return False

    def add_workflow(self, workflow: Workflow) -> bool:
        # Check if workflow with same name already exists
        for existing in self.workflows:
            if existing.name == workflow.name:
                return False
        
        self.workflows.append(workflow)
        return True

    def remove_workflow(self, name: str) -> bool:
        for i, workflow in enumerate(self.workflows):
            if workflow.name == name:
                del self.workflows[i]
                return True
        return False

    def add_mcp_url(self, url: str) -> bool:
        if url not in self.mcp_urls:
            self.mcp_urls.append(url)
            return True
        return False

    def remove_mcp_url(self, url: str) -> bool:
        if url in self.mcp_urls:
            self.mcp_urls.remove(url)
            return True
        return False


if __name__ == "__main__":
    config = Config.load()
    print(config)
    config.add_workflow(Workflow(name="test", overall_goal="test", steps=[VibeStepMetadata(name="test", goal="test", hint="test")]))
    config.save()
