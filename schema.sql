DROP TABLE IF EXISTS `users`;

CREATE TABLE `users` (
	`id` int unsigned NOT NULL AUTO_INCREMENT,
	`username` varchar(64) NOT NULL UNIQUE,
	`password` char(64) NOT NULL,
	`salt` char(32) NOT NULL,
	PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
