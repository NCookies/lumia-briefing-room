import { GUIDE_FOLDER_TREE, GUIDE_SECTIONS } from '../guide'

/** 풀영상·후보·클립·폴더 구조를 설명하는 안내. 첫 실행 화면과 `?` 모달이 같이 쓴다. 그림은 코드로 그린다. */
export function GuideContent() {
  return (
    <div className="flex flex-col gap-4 text-sm text-zinc-200">
      {GUIDE_SECTIONS.map((section) => (
        <section key={section.title} className="flex flex-col gap-1">
          <h3 className="text-base font-medium text-zinc-100">{section.title}</h3>
          {section.body.map((line) => (
            <p key={line} className="leading-relaxed text-zinc-300">
              {line}
            </p>
          ))}
          {section.title === '폴더 구조' && (
            <pre className="overflow-x-auto rounded border border-zinc-700 bg-zinc-900 p-3 font-mono text-xs leading-relaxed text-zinc-300">{GUIDE_FOLDER_TREE}</pre>
          )}
        </section>
      ))}
    </div>
  )
}
