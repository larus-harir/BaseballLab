"""Stable machine IDs stay in files; display names are Korean."""
LABELS = {
    'E01': '타자·투수 경쟁 진화 연구', 'random': '무작위형', 'aggressive': '적극 공격형',
    'patient': '인내형', 'mixed': '구종 혼합형', 'strike_first': '스트라이크 우선형',
    'take': '기다리기', 'contact': '컨택 스윙', 'power': '강공 스윙', 'bunt': '번트',
    'fastball': '직구', 'breaking': '변화구', 'changeup': '체인지업',
    'synthetic_demo': '합성 야구 환경', 'synthetic-v1': '합성 타석 모델 1',
    'walk': '볼넷', 'strikeout': '삼진', 'out': '아웃', 'ground_out': '땅볼 아웃',
    'bunt_out': '번트 아웃', 'single': '단타', 'double': '2루타', 'triple': '3루타',
    'home_run': '홈런', 'ball': '볼', 'strike': '스트라이크', 'foul': '파울',
    'random_team': '무작위 팀', 'attack_team': '적극 공격·혼합 투구 팀',
    'patient_team': '인내·스트라이크 우선 팀', 'initial': '학습 전 신경망',
}


def korean(value: str) -> str:
    return LABELS.get(value, value)
