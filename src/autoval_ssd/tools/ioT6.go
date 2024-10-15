package main

import (
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/signal"
	"runtime"
	"sync/atomic"
	"syscall"
	"time"
)

var ioc chan int
var stats chan time.Duration
var file *os.File
var size = flag.Int64("size", 1, "arena size in gigabytes")
var hz = flag.Float64("rate", 384, "rate in Hz")
var block = flag.Int64("block", 64, "block size in kilobytes")
var total int64
var totalDuration time.Duration
var maxDuration time.Duration
var maxPending int32
var pending int32

func worker() {
	buf := make([]byte, *block*1024)
	boundary := *size * 1024 * 1024 * 1024
	for range ioc {
		pos := rand.Int63n(boundary/4096) * 4096
		p := atomic.AddInt32(&pending, 1)
		if p > maxPending {
			maxPending = p
		}
		start := time.Now()
		_, err := file.WriteAt(buf, pos)
		if err != nil {
			log.Println(err)
		}
		elapsed := time.Since(start)
		atomic.AddInt32(&pending, -1)
		stats <- elapsed
	}
}

func generator() {
	duration := time.Duration(0)
	if *hz != 0 {
		duration = time.Second / time.Duration(*hz)
	}
	overhead := time.Duration(0)

	start := time.Now()
	previous := start

	for {
		ioc <- 1

		elapsed := start.Sub(previous)

		overhead += (elapsed - duration)

		if overhead > duration {
			overhead -= duration
		} else {
			time.Sleep(duration)
		}

		previous = start
		start = time.Now()
	}
}

func aggregate() {
	for d := range stats {
		total++
		totalDuration += d
		if maxDuration < d {
			maxDuration = d
		}
	}
}

func statistics() {
	last := int64(0)
	lastDuration := time.Duration(0)

	for {
		time.Sleep(time.Second)
		sampleDuration := totalDuration - lastDuration
		if maxDuration > (time.Duration(10)*time.Millisecond) || maxPending > 10 {
			fmt.Println(time.Now(), " ", maxDuration, sampleDuration/time.Duration(total-last), maxPending)
		}
		last = total
		lastDuration = totalDuration
		maxDuration = time.Duration(0)
		maxPending = 0
	}
}

func init() {
	flag.Parse()
	runtime.GOMAXPROCS(32)
}

func main() {
	var err error
	ioc = make(chan int, 10000)
	stats = make(chan time.Duration, 100)
	flag.Parse()
	file, err = os.OpenFile(flag.Arg(0), syscall.O_DIRECT|os.O_RDWR, 0)
	if err != nil {
		panic(err)
	}
	for i := 0; i < 1000; i++ {
		go worker()
	}
	go aggregate()
	go generator()
	go statistics()
	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c
	// panic("interrupted")
}
