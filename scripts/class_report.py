# -*- coding: utf-8 -*-
"""
班级学情分析报告生成脚本

本脚本用于生成班级阅读答题学情分析报告
"""

import json
from typing import Dict, List
from datetime import datetime


class ClassReportBuilder:
    """班级报告构建器"""
    
    def __init__(self, class_name: str, grade: int, topic: str):
        self.class_name = class_name
        self.grade = grade
        self.topic = topic
        self.student_data = []
    
    def add_student_result(self, student_name: str, result: Dict):
        """添加学生评估结果"""
        self.student_data.append({
            'name': student_name,
            'result': result
        })
    
    def build_report(self) -> Dict:
        """构建完整报告"""
        report = {
            'basic_info': {
                'class_name': self.class_name,
                'grade': self.grade,
                'topic': self.topic,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'total_students': len(self.student_data)
            },
            'overview': self._generate_overview(),
            'point_analysis': self._analyze_points(),
            'teaching_suggestions': self._generate_teaching_suggestions()
        }
        
        return report
    
    def _generate_overview(self) -> Dict:
        """生成整体概览"""
        total = len(self.student_data)
        if total == 0:
            return {}
        
        complete = sum(1 for s in self.student_data 
                       if self._is_complete(s['result']))
        partial = sum(1 for s in self.student_data 
                     if self._is_partial(s['result']))
        
        return {
            'complete': complete,
            'complete_rate': round(complete / total * 100, 1),
            'partial': partial,
            'partial_rate': round(partial / total * 100, 1),
            'needs_improvement': total - complete - partial,
            'needs_improvement_rate': round((total - complete - partial) / total * 100, 1)
        }
    
    def _is_complete(self, result: Dict) -> bool:
        """判断是否全面"""
        evaluations = result.get('point_evaluations', [])
        return all(e['status'] == 'complete' for e in evaluations)
    
    def _is_partial(self, result: Dict) -> bool:
        """判断是否基本全面"""
        evaluations = result.get('point_evaluations', [])
        if not evaluations:
            return False
        complete_count = sum(1 for e in evaluations if e['status'] == 'complete')
        return complete_count >= len(evaluations) * 0.6
    
    def _analyze_points(self) -> List[Dict]:
        """分析各要点掌握情况"""
        # 汇总所有要点的覆盖情况
        point_stats = {}
        
        for student in self.student_data:
            result = student['result']
            for eval_item in result.get('point_evaluations', []):
                label = eval_item['label']
                if label not in point_stats:
                    point_stats[label] = {'complete': 0, 'partial': 0, 'missing': 0}
                point_stats[label][eval_item['status']] += 1
        
        total = len(self.student_data)
        analysis = []
        
        for label, stats in point_stats.items():
            miss_rate = round(stats['missing'] / total * 100, 1) if total > 0 else 0
            analysis.append({
                'point': label,
                'complete_count': stats['complete'],
                'complete_rate': round(stats['complete'] / total * 100, 1) if total > 0 else 0,
                'partial_count': stats['partial'],
                'missing_count': stats['missing'],
                'missing_rate': miss_rate,
                'highlight': miss_rate > 60  # 超过60%遗漏标记为高亮
            })
        
        return sorted(analysis, key=lambda x: x['missing_rate'], reverse=True)
    
    def _generate_teaching_suggestions(self) -> List[Dict]:
        """生成教学建议"""
        suggestions = []
        
        # 基于高遗漏率要点生成建议
        for point in self._analyze_points():
            if point['highlight']:
                suggestions.append({
                    'point': point['point'],
                    'missing_rate': point['missing_rate'],
                    'suggestion': f"在{point['point']}方面需要加强教学，建议设计专项练习。"
                })
        
        return suggestions
    
    def export_to_dict(self) -> Dict:
        """导出为字典"""
        return self.build_report()
    
    def export_to_text(self) -> str:
        """导出为文本格式"""
        report = self.build_report()
        
        lines = []
        lines.append("=" * 50)
        lines.append("班级学情分析报告")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"班级：{report['basic_info']['class_name']}")
        lines.append(f"年级：{report['basic_info']['grade']}年级")
        lines.append(f"题目：{report['basic_info']['topic']}")
        lines.append(f"统计时间：{report['basic_info']['generated_at']}")
        lines.append(f"总人数：{report['basic_info']['total_students']}")
        lines.append("")
        lines.append("-" * 50)
        lines.append("整体情况")
        lines.append("-" * 50)
        lines.append(f"全面：{report['overview']['complete']}人（{report['overview']['complete_rate']}%）")
        lines.append(f"基本全面：{report['overview']['partial']}人（{report['overview']['partial_rate']}%）")
        lines.append(f"需改进：{report['overview']['needs_improvement']}人（{report['overview']['needs_improvement_rate']}%）")
        lines.append("")
        lines.append("-" * 50)
        lines.append("要点分析")
        lines.append("-" * 50)
        
        for point in report['point_analysis']:
            status = "⚠️" if point['highlight'] else "✓"
            lines.append(f"{status} {point['point']}")
            lines.append(f"   完整：{point['complete_rate']}% | 遗漏：{point['missing_rate']}%")
        
        lines.append("")
        lines.append("-" * 50)
        lines.append("教学建议")
        lines.append("-" * 50)
        
        for i, sug in enumerate(report['teaching_suggestions'], 1):
            lines.append(f"{i}. {sug['suggestion']}")
        
        return "\n".join(lines)


def generate_sample_report() -> Dict:
    """生成示例报告"""
    builder = ClassReportBuilder(
        class_name="三年级一班",
        grade=3,
        topic="说说课文描写了哪些景物？给你印象最深的是什么？"
    )
    
    # 添加示例数据
    sample_results = [
        {
            'point_evaluations': [
                {'label': '景物识别', 'status': 'complete'},
                {'label': '印象最深', 'status': 'partial'}
            ]
        },
        {
            'point_evaluations': [
                {'label': '景物识别', 'status': 'complete'},
                {'label': '印象最深', 'status': 'complete'}
            ]
        }
    ]
    
    for i, result in enumerate(sample_results):
        builder.add_student_result(f"学生{i+1}", result)
    
    return builder.build_report()


if __name__ == '__main__':
    report = generate_sample_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
