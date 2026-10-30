# The Thinning Dark

[![Generator is Hugo](https://img.shields.io/badge/Generator%20is-Hugo-ff4088?&logo=hugo)](https://github.com/gohugoio/hugo) [![Theme is MemE](https://img.shields.io/badge/Theme%20is-MemE-2a6df4)](https://github.com/reuixiy/hugo-theme-meme) [![Source on GitHub](https://img.shields.io/badge/Source%20on-GitHub-181717?&logo=github)](https://github.com/dawnow/blog) [![Built on Netlify](https://img.shields.io/badge/Built%20on-Netlify-00c7b7?&logo=netlify)](https://www.netlify.com/)

- https://thethinningdark.com/
- https://thethinningdark.netlify.app/

## 构建

```bash
hugo --gc --minify      # 本地构建，用仓库里已提交的字体子集
npm run build           # 完整构建：Hugo → 重切字体子集 → 生成 Service Worker
npm run check:fonts     # 检查当前页面的用字是否都被已提交的子集覆盖
npm run fonts           # 手动重切字体子集
```

字体分两层：`fonts-src/` 是完整字库（不进部署产物），`static/fonts/*-subset.woff2` 是按全站
用字切好的子集。Netlify 构建时会按当次页面重切一次，并给文件名加上按字集算出的哈希，所以
新增文章带出新字时不需要手动处理；只有本地预览想看到最新子集时，才需要跑一次 `npm run fonts`。

<a rel="license" href="http://creativecommons.org/licenses/by-nc-sa/4.0/"><img style="border-width:0" src="https://i.creativecommons.org/l/by-nc-sa/4.0/88x31.png" /></a>
