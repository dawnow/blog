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
            // 字体不预缓存：/fonts/* 已经是 immutable 的 HTTP 缓存，
            // 再放进 SW 会让每个访客在后台多下 1.4 MB（甚至更多）。
            "**/*.{html,css,js,json}"
        ],
        modifyURLPrefix: {
            "": "./"
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