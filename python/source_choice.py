class SourceChoiceRequired(ValueError):
    def __init__(self,options):
        super().__init__('暂未确认原唱音源，请先询问用户是否接受下面的其他或未注明歌手版本；同意后再用对应 source_url，不要自行换人演唱')
        self.options=options[:3]
