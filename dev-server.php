<?php
/**
 * dev-server.php — router for PHP's built-in server, so that local previewing
 * behaves like the real host.
 *
 * Run it through the Makefile:
 *
 *     make preview
 *
 * or directly:
 *
 *     php -S localhost:8000 -t public dev-server.php
 *
 * PHP's built-in server has no DirectoryIndex, no DirectorySlash and no
 * .htaccess. Without a router, "/" would 404, "/icfem/2026" without the
 * trailing slash would 404, and the deny rules protecting cache/ and _data/
 * would not apply — so a local check would tell you nothing about the real
 * thing. This reproduces the four behaviours that matter.
 *
 * It is a development tool. It is never uploaded: `make deploy` sends only
 * public/, and this file sits outside it.
 */

declare(strict_types=1);

$root = __DIR__ . '/public';
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) ?? '/';
$path = rawurldecode($path);

// Refuse anything trying to climb out of public/.
if (str_contains($path, '..')) {
    http_response_code(403);
    echo 'Forbidden';
    return true;
}

// Mirror the deny rules in cache/.htaccess and _data/.htaccess.
foreach (['/cache/', '/_data/'] as $private) {
    if (str_starts_with($path, $private)) {
        http_response_code(403);
        echo 'Forbidden — this directory is denied by .htaccess in production too.';
        return true;
    }
}

$target = $root . $path;

// A real file: let the built-in server handle it, including running .php.
if ($path !== '/' && is_file($target)) {
    return false;
}

// DirectorySlash: /icfem/2026 -> /icfem/2026/
if (is_dir($target) && !str_ends_with($path, '/')) {
    header('Location: ' . $path . '/', true, 301);
    return true;
}

// DirectoryIndex, with the front page standing in for the site root.
if ($path === '/' || is_dir($target)) {
    $front = 'future';
    $config = __DIR__ . '/site.toml';
    if (is_readable($config)
        && preg_match('/^front_page\s*=\s*"([^"]+)"/m', file_get_contents($config), $m)) {
        $front = $m[1];
    }

    $candidates = rtrim($target, '/') . '/index.html';
    if ($path === '/') {
        // The front page is PHP and lives at the root under its configured name.
        $php = $root . '/' . $front . '.php';
        if (is_file($php)) {
            $_SERVER['SCRIPT_NAME'] = '/' . $front . '.php';
            require $php;
            return true;
        }
    }
    if (is_file($candidates)) {
        header('Content-Type: text/html; charset=utf-8');
        readfile($candidates);
        return true;
    }
}

// Everything else: the generated 404 if there is one.
http_response_code(404);
$notFound = $root . '/404.html';
if (is_file($notFound)) {
    readfile($notFound);
} else {
    echo '<!DOCTYPE html><meta charset="utf-8"><title>Not found</title>'
       . '<h1>404</h1><p>No page at <code>' . htmlspecialchars($path) . '</code>.</p>'
       . '<p><a href="/">Back to the list</a></p>';
}
return true;
