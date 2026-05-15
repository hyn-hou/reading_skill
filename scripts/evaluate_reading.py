#!/usr/bin/env python3
"""
小学阅读答题全面性评估 - 核心评估脚本
支持单张和批量图片评估（PNG/JPG/JPEG，最多50张/批次）
"""

import os
import sys
import json
import time
import base64
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# ============ 配置区 ============
SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.JPEG'}
MAX_BATCH_SIZE = 50  # 单批次最大处理数量
OCR_CONFIDENCE_THRESHOLD = 0.7  # OCR置信度阈值
# ================================


@dataclass
class StudentAnswer:
    """学生答题数据"""
    student_id: str
    image_path: str
    recognized_text: str = ""
    confidence: float = 0.0
    low_confidence_words: List[Tuple[str, List[str]]] = field(default_factory=list)  # [(word, [alternatives])]
    evaluation: Optional[Dict] = None
    status: str = "pending"  # pending, processing, completed, error
    error_message: str = ""


@dataclass
class ClassReport:
    """班级学情报告"""
    total_count: int = 0
    comprehensive_rate: float = 0.0  # 全面率
    basic_rate: float = 0.0  # 基本全面率
    needs_improve_rate: float = 0.0  # 需改进率
    point_coverage: Dict[str, Dict] = field(dict)  # {point: {full: n, partial: n, missing: n}}
    high_miss_points: List[Dict] = field(list)  # 遗漏率>60%的要点
    best_examples: List[Dict] = field(list)  # 最佳作答
    common_mistakes: List[Dict] = field(list)  # 常见遗漏


class ReadingEvaluator:
    """阅读答题评估器"""
    
    def __init__(self, grade: int, question: str, reference_points: List[str], 
                 context: str = "", api_key: str = None):
        self.grade = grade
        self.question = question
        self.reference_points = reference_points
        self.context = context
        self.api_key = api_key
        self.prompts = self._load_prompts()
    
    def _load_prompts(self) -> Dict:
        """加载提示词模板"""
        # 这里可以加载 references/提示词模板.md
        return {
            "single_evaluation": self._get_single_prompt(),
            "batch_evaluation": self._get_batch_prompt(),
        }
    
    def _get_single_prompt(self) -> str:
        """获取单张评估提示词"""
        grade_names = {1: "一年级", 2: "二年级", 3: "三年级", 4: "四年级", 
                      5: "五年级", 6: "六年级"}
        grade_name = grade_names.get(self.grade, f"{self.grade}年级")
        
        points_text = "\n".join([f"{i+1}. {p}" for i, p in enumerate(self.reference_points)])
        
        return f"""你是一位专业的小学语文教师，正在评估{grade_name}学生的阅读理解答题情况。

【任务】
请根据以下参考答案要点，对学生的作答进行逐要点评价。

【题目】
{self.question}

【阅读文本】
{self.context}

【参考答案要点】
{points_text}

【学生作答】
{{student_answer}}

【评估要求】
1. 逐要点分析学生作答是否覆盖参考答案中的每个要点
2. 对于每个要点，明确判断：✅完整覆盖 / ⚠️部分覆盖 / ❌缺失
3. 识别学生答案中超出参考答案但合理的额外亮点（标记为💡）
4. 使用{grade_name}学生能理解的语言给出评价
5. 评价要正向、有建设性

【输出格式】请严格按以下格式输出：
## 📝 识别原文
[学生作答文本]

## 📊 整体结论
[回答全面性评级：优秀/良好/需改进] + 简要说明

## 🔍 逐要点评价
| 要点 | 覆盖情况 | 具体评价 |
|------|----------|----------|
| {{point_1}} | [✅/⚠️/❌] | [评价] |

## ✏️ 修改建议
[针对未覆盖要点的具体建议]"""
    
    def _get_batch_prompt(self) -> str:
        """获取批量评估提示词"""
        grade_name = f"{self.grade}年级"
        points_text = "\n".join([f"{i+1}. {p}" for i, p in enumerate(self.reference_points)])
        
        return f"""你是一位专业的小学语文教师，正在对多份{grade_name}学生阅读答题进行批量评估。

【任务】
对这{len(self.reference_points)}份答案进行批量分析，输出统计和薄弱点。

【题目】
{self.question}

【参考答案要点】
{points_text}

【学生作答列表】
{{student_answers}}

【评估要求】
1. 对每份答案简要判断：全面/基本全面/不够全面
2. 统计每个要点的全班覆盖比例
3. 识别高遗漏率要点（>60%标记为⚠️）
4. 抽取最佳作答和常见遗漏写法

【输出格式】
## 📈 班级整体统计
[统计表格]

## ⚠️ 集中薄弱点
[高遗漏率要点及教学建议]

## 📋 典型样例
### ✅ 最佳作答
### ❌ 常见遗漏写法"""
    
    def process_image(self, image_path: str) -> StudentAnswer:
        """处理单张图片"""
        student_id = Path(image_path).stem
        
        # 1. 图像预处理
        processed_image = self._preprocess_image(image_path)
        
        # 2. OCR识别
        recognized_text, confidence, low_conf_words = self._ocr_recognize(processed_image)
        
        # 3. 错别字纠正
        corrected_text = self._fix_errors(recognized_text)
        
        # 4. 语义评估
        evaluation = self._evaluate_answer(corrected_text)
        
        return StudentAnswer(
            student_id=student_id,
            image_path=image_path,
            recognized_text=corrected_text,
            confidence=confidence,
            low_confidence_words=low_conf_words,
            evaluation=evaluation,
            status="completed"
        )
    
    def _preprocess_image(self, image_path: str) -> str:
        """图像预处理（倾斜校正、亮度调整等）"""
        # 这里集成图像处理逻辑
        # 实际实现可使用 OpenCV 或 PIL
        return image_path
    
    def _ocr_recognize(self, image_path: str) -> Tuple[str, float, List]:
        """
        OCR识别
        返回: (识别文本, 置信度, [(低置信度词, 备选词列表)])
        """
        # 这里集成OCR能力（可用百度OCR、腾讯OCR等）
        # 返回格式: (text, confidence, [(word, alternatives)])
        raise NotImplementedError("请集成OCR服务")
    
    def _fix_errors(self, text: str) -> str:
        """错别字自动纠正"""
        # 常见错别字映射
        error_map = {
            r'已后': '以后',
            r'在那': '在那',
            # 添加更多映射...
        }
        
        corrected = text
        for error, correct in error_map.items():
            corrected = re.sub(error, correct, corrected)
        
        return corrected
    
    def _evaluate_answer(self, student_answer: str) -> Dict:
        """评估答案（调用LLM）"""
        # 这里调用大语言模型进行评估
        # 使用 self._get_single_prompt() 格式化后调用
        raise NotImplementedError("请集成LLM服务")
    
    def batch_process(self, image_paths: List[str], 
                     progress_callback=None) -> List[StudentAnswer]:
        """
        批量处理多张图片
        
        Args:
            image_paths: 图片路径列表（最多50张）
            progress_callback: 进度回调函数 callback(current, total)
        
        Returns:
            评估结果列表
        """
        if len(image_paths) > MAX_BATCH_SIZE:
            raise ValueError(f"单批次最多处理{MAX_BATCH_SIZE}张图片")
        
        results = []
        total = len(image_paths)
        
        # 并发处理
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_path = {
                executor.submit(self.process_image, path): path 
                for path in image_paths
            }
            
            completed = 0
            for future in as_completed(future_to_path):
                completed += 1
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    path = future_to_path[future]
                    results.append(StudentAnswer(
                        student_id=Path(path).stem,
                        image_path=path,
                        status="error",
                        error_message=str(e)
                    ))
                
                if progress_callback:
                    progress_callback(completed, total)
        
        return results
    
    def generate_class_report(self, results: List[StudentAnswer]) -> ClassReport:
        """生成班级学情报告"""
        if len(results) < 10:
            print("⚠️ 样本量小于10份，不生成班级报告")
            return None
        
        report = ClassReport()
        report.total_count = len(results)
        
        # 统计各评级数量
        comprehensive = sum(1 for r in results if r.evaluation and 
                           r.evaluation.get('rating') == '优秀')
        basic = sum(1 for r in results if r.evaluation and 
                   r.evaluation.get('rating') == '良好')
        needs_improve = sum(1 for r in results if r.evaluation and 
                          r.evaluation.get('rating') == '需改进')
        
        report.comprehensive_rate = comprehensive / report.total_count
        report.basic_rate = basic / report.total_count
        report.needs_improve_rate = needs_improve / report.total_count
        
        # 要点覆盖统计
        for i, point in enumerate(self.reference_points):
            full = sum(1 for r in results if r.evaluation and 
                      r.evaluation.get('points', {}).get(i, {}).get('status') == '完整覆盖')
            partial = sum(1 for r in results if r.evaluation and 
                         r.evaluation.get('points', {}).get(i, {}).get('status') == '部分覆盖')
            missing = sum(1 for r in results if r.evaluation and 
                         r.evaluation.get('points', {}).get(i, {}).get('status') == '缺失')
            
            miss_rate = missing / report.total_count
            report.point_coverage[point] = {
                'full': full, 'partial': partial, 'missing': missing,
                'miss_rate': miss_rate
            }
            
            if miss_rate > 0.6:
                report.high_miss_points.append({
                    'point': point,
                    'miss_rate': miss_rate,
                    'count': missing
                })
        
        # 抽取典型样例
        report.best_examples = [
            {'id': r.student_id, 'text': r.recognized_text, 
             'eval': r.evaluation.get('summary', '')}
            for r in results if r.evaluation and r.evaluation.get('rating') == '优秀'
        ][:3]
        
        report.common_mistakes = [
            {'id': r.student_id, 'text': r.recognized_text,
             'missed_points': r.evaluation.get('missed_points', [])}
            for r in results if r.evaluation and r.evaluation.get('rating') == '需改进'
        ][:3]
        
        return report


def validate_image_format(image_path: str) -> bool:
    """验证图片格式"""
    ext = Path(image_path).suffix
    return ext in SUPPORTED_FORMATS


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='小学阅读答题评估')
    parser.add_argument('--images', nargs='+', required=True, help='图片路径（最多50张）')
    parser.add_argument('--grade', type=int, required=True, help='年级（1-6）')
    parser.add_argument('--question', type=str, required=True, help='题目内容')
    parser.add_argument('--points', nargs='+', required=True, help='参考答案要点')
    parser.add_argument('--context', type=str, default='', help='阅读文本（可选）')
    parser.add_argument('--output', type=str, default='report.json', help='输出文件')
    parser.add_argument('--batch-report', action='store_true', help='生成班级报告')
    
    args = parser.parse_args()
    
    # 验证图片格式
    valid_images = [img for img in args.images if validate_image_format(img)]
    invalid_count = len(args.images) - len(valid_images)
    
    if invalid_count > 0:
        print(f"⚠️ 跳过{invalid_count}张不支持格式的图片")
    
    if not valid_images:
        print("❌ 没有有效的图片文件")
        return
    
    print(f"📷 开始处理 {len(valid_images)} 张图片...")
    
    # 初始化评估器
    evaluator = ReadingEvaluator(
        grade=args.grade,
        question=args.question,
        reference_points=args.points,
        context=args.context
    )
    
    # 批量处理
    def progress(current, total):
        print(f"📊 进度: {current}/{total} ({current*100//total}%)")
    
    results = evaluator.batch_process(valid_images, progress_callback=progress)
    
    # 输出结果
    output_data = {
        'total': len(results),
        'completed': sum(1 for r in results if r.status == 'completed'),
        'errors': sum(1 for r in results if r.status == 'error'),
        'results': [
            {
                'id': r.student_id,
                'text': r.recognized_text,
                'confidence': r.confidence,
                'evaluation': r.evaluation,
                'status': r.status,
                'error': r.error_message
            }
            for r in results
        ]
    }
    
    # 生成班级报告
    if args.batch_report and len(results) >= 10:
        report = evaluator.generate_class_report(results)
        output_data['class_report'] = {
            'total_count': report.total_count,
            'comprehensive_rate': f"{report.comprehensive_rate:.1%}",
            'basic_rate': f"{report.basic_rate:.1%}",
            'needs_improve_rate': f"{report.needs_improve_rate:.1%}",
            'high_miss_points': report.high_miss_points,
            'best_examples': report.best_examples,
            'common_mistakes': report.common_mistakes
        }
    
    # 保存结果
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 评估完成，结果已保存到 {args.output}")


if __name__ == '__main__':
    main()
