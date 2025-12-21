"""
Script Generator - converts trace into executable code
"""

import json
from typing import List, Optional
from .recorder import Trace, TraceStep
from .query import find


class ScriptGenerator:
    """Generates Python or TypeScript code from a trace"""
    
    def __init__(self, trace: Trace):
        self.trace = trace
    
    def generate_python(self) -> str:
        """Generate Python script from trace"""
        lines = [
            '"""',
            f'Generated script from trace: {self.trace.start_url}',
            f'Created: {self.trace.created_at}',
            '"""',
            '',
            'from sentience import SentienceBrowser, snapshot, find, click, type_text, press',
            '',
            'def main():',
            '    with SentienceBrowser(headless=False) as browser:',
            f'        browser.page.goto("{self.trace.start_url}")',
            '        browser.page.wait_for_load_state("networkidle")',
            '',
        ]
        
        for step in self.trace.steps:
            lines.extend(self._generate_python_step(step, indent='        '))
        
        lines.extend([
            '',
            'if __name__ == "__main__":',
            '    main()',
        ])
        
        return '\n'.join(lines)
    
    def generate_typescript(self) -> str:
        """Generate TypeScript script from trace"""
        lines = [
            '/**',
            f' * Generated script from trace: {self.trace.start_url}',
            f' * Created: {self.trace.created_at}',
            ' */',
            '',
            "import { SentienceBrowser, snapshot, find, click, typeText, press } from './src';",
            '',
            'async function main() {',
            '  const browser = new SentienceBrowser(undefined, false);',
            '',
            '  try {',
            '    await browser.start();',
            f'    await browser.getPage().goto(\'{self.trace.start_url}\');',
            '    await browser.getPage().waitForLoadState(\'networkidle\');',
            '',
        ]
        
        for step in self.trace.steps:
            lines.extend(self._generate_typescript_step(step, indent='    '))
        
        lines.extend([
            '  } finally {',
            '    await browser.close();',
            '  }',
            '}',
            '',
            'main().catch(console.error);',
        ])
        
        return '\n'.join(lines)
    
    def _generate_python_step(self, step: TraceStep, indent: str = '') -> List[str]:
        """Generate Python code for a single step"""
        lines = []
        
        if step.type == 'navigation':
            lines.append(f'{indent}# Navigate to {step.url}')
            lines.append(f'{indent}browser.page.goto("{step.url}")')
            lines.append(f'{indent}browser.page.wait_for_load_state("networkidle")')
        
        elif step.type == 'click':
            if step.selector:
                # Use semantic selector
                lines.append(f'{indent}# Click: {step.selector}')
                lines.append(f'{indent}snap = snapshot(browser)')
                lines.append(f'{indent}element = find(snap, "{step.selector}")')
                lines.append(f'{indent}if element:')
                lines.append(f'{indent}    click(browser, element.id)')
                lines.append(f'{indent}else:')
                lines.append(f'{indent}    raise Exception("Element not found: {step.selector}")')
            elif step.element_id is not None:
                # Fallback to element ID
                lines.append(f'{indent}# TODO: replace with semantic selector')
                lines.append(f'{indent}click(browser, {step.element_id})')
            lines.append('')
        
        elif step.type == 'type':
            if step.selector:
                lines.append(f'{indent}# Type into: {step.selector}')
                lines.append(f'{indent}snap = snapshot(browser)')
                lines.append(f'{indent}element = find(snap, "{step.selector}")')
                lines.append(f'{indent}if element:')
                lines.append(f'{indent}    type_text(browser, element.id, "{step.text}")')
                lines.append(f'{indent}else:')
                lines.append(f'{indent}    raise Exception("Element not found: {step.selector}")')
            elif step.element_id is not None:
                lines.append(f'{indent}# TODO: replace with semantic selector')
                lines.append(f'{indent}type_text(browser, {step.element_id}, "{step.text}")')
            lines.append('')
        
        elif step.type == 'press':
            lines.append(f'{indent}# Press key: {step.key}')
            lines.append(f'{indent}press(browser, "{step.key}")')
            lines.append('')
        
        return lines
    
    def _generate_typescript_step(self, step: TraceStep, indent: str = '') -> List[str]:
        """Generate TypeScript code for a single step"""
        lines = []
        
        if step.type == 'navigation':
            lines.append(f'{indent}// Navigate to {step.url}')
            lines.append(f'{indent}await browser.getPage().goto(\'{step.url}\');')
            lines.append(f'{indent}await browser.getPage().waitForLoadState(\'networkidle\');')
        
        elif step.type == 'click':
            if step.selector:
                lines.append(f'{indent}// Click: {step.selector}')
                lines.append(f'{indent}const snap = await snapshot(browser);')
                lines.append(f'{indent}const element = find(snap, \'{step.selector}\');')
                lines.append(f'{indent}if (element) {{')
                lines.append(f'{indent}  await click(browser, element.id);')
                lines.append(f'{indent}}} else {{')
                lines.append(f'{indent}  throw new Error(\'Element not found: {step.selector}\');')
                lines.append(f'{indent}}}')
            elif step.element_id is not None:
                lines.append(f'{indent}// TODO: replace with semantic selector')
                lines.append(f'{indent}await click(browser, {step.element_id});')
            lines.append('')
        
        elif step.type == 'type':
            if step.selector:
                lines.append(f'{indent}// Type into: {step.selector}')
                lines.append(f'{indent}const snap = await snapshot(browser);')
                lines.append(f'{indent}const element = find(snap, \'{step.selector}\');')
                lines.append(f'{indent}if (element) {{')
                lines.append(f'{indent}  await typeText(browser, element.id, \'{step.text}\');')
                lines.append(f'{indent}}} else {{')
                lines.append(f'{indent}  throw new Error(\'Element not found: {step.selector}\');')
                lines.append(f'{indent}}}')
            elif step.element_id is not None:
                lines.append(f'{indent}// TODO: replace with semantic selector')
                lines.append(f'{indent}await typeText(browser, {step.element_id}, \'{step.text}\');')
            lines.append('')
        
        elif step.type == 'press':
            lines.append(f'{indent}// Press key: {step.key}')
            lines.append(f'{indent}await press(browser, \'{step.key}\');')
            lines.append('')
        
        return lines
    
    def save_python(self, filepath: str) -> None:
        """Generate and save Python script"""
        code = self.generate_python()
        with open(filepath, 'w') as f:
            f.write(code)
    
    def save_typescript(self, filepath: str) -> None:
        """Generate and save TypeScript script"""
        code = self.generate_typescript()
        with open(filepath, 'w') as f:
            f.write(code)


def generate(trace: Trace, language: str = 'py') -> str:
    """
    Generate script from trace
    
    Args:
        trace: Trace object
        language: 'py' or 'ts'
    
    Returns:
        Generated code as string
    """
    generator = ScriptGenerator(trace)
    if language == 'py':
        return generator.generate_python()
    elif language == 'ts':
        return generator.generate_typescript()
    else:
        raise ValueError(f"Unsupported language: {language}. Use 'py' or 'ts'")

