const gulp = require("gulp");
const workbox = require("workbox-build");
const uglifyes = require('uglify-es');
const composer = require('gulp-uglify/composer');
const uglify = composer(uglifyes, console);
const pipeline = require('readable-stream').pipeline;

gulp.task('generate-service-worker', () => {
    return workbox.injectManifest({
        swSrc: './sw-template.js',
        swDest: './public/sw.js',
        globDirectory: './public',
        globPatterns: [
            // 只预缓存应用外壳。页面不进预缓存：导航由 SW 的 NetworkFirst
            // 处理，这样部署后第一次访问就是新内容，访客也不必在后台
            // 下载整站（约 2 MB）。
            "offline.html",
            "manifest.json",
            "favicon.ico",
            "css/**/*.css",
            "js/*.js",
            "icons/*"
        ],
        // 让预缓存清单用绝对路径，这样 matchPrecache('/offline.html') 能精确命中
        modifyURLPrefix: {
            "": "/"
        }
    });
});

gulp.task("uglify", function () {
    return pipeline(
        gulp.src("./public/sw.js"),
        uglify(),
        gulp.dest("./public")
    );
});

gulp.task("build", gulp.series("generate-service-worker", "uglify"));